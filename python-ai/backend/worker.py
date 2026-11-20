import json
import multiprocessing
import threading
import time
from pathlib import Path
from requests import Timeout
from . import config
from .content_exporter import result_bundle
from .file_storage import validate_file
from .job_store import Store
from .knowledge_extractor import derive_points
from .practice_quality import looks_like_ocr_table, split_practice_text, usable_practice_text
from .practice_variety import EXHAUSTED, REPEATED, PracticePlan
from .schemas import Point

def run_job_process(root, job, store_type=Store):
    # Each task owns its parser and HTTP connections. No shared IPC locks/queues
    # are terminated; SQLite transactions protect committed checkpoints.
    store=store_type(Path(root))
    try:Runner(store).run(job)
    except Exception as exc:store.update(job['id'],'failed','处理失败',error=f'{type(exc).__name__}: {exc}'[:500])

class Runner:
    def __init__(self,store):self.store=store;self.stop=threading.Event();self.thread=None;self.lock=None
    def start(self):
        # OS lock prevents a second Uvicorn process from recovering a live worker's jobs.
        self.lock=open(self.store.root/'worker.lock','a+b');self.lock.seek(0);self.lock.write(b'0');self.lock.flush();self.lock.seek(0)
        try:
            import msvcrt
            msvcrt.locking(self.lock.fileno(),msvcrt.LK_NBLCK,1)
        except ImportError:
            import fcntl
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.store.recover()
        self.thread=threading.Thread(target=self.loop,daemon=True,name='ai-worker');self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=5)
        if self.thread and self.thread.is_alive():return
        if self.lock:self.lock.close()
    def loop(self):
        while not self.stop.is_set():
            job=self.store.claim()
            if job:
                try:self.supervise(job)
                except Exception as exc:self.store.update(job['id'],'failed','处理失败',error=f'{type(exc).__name__}: {exc}'[:500])
            else:self.stop.wait(.4)
    def supervise(self,job,target=run_job_process):
        args=(str(self.store.root),job)
        if target is run_job_process:
            args+=(type(self.store),)
        process=multiprocessing.get_context('spawn').Process(target=target,args=args,daemon=True)
        try:
            if not self.cancelled(job):
                process.start()
                while process.is_alive():
                    if self.cancelled(job):
                        process.terminate();process.join(timeout=2)
                        if process.is_alive():process.kill();process.join(timeout=2)
                        break
                    process.join(timeout=.1)
            # Read only after the child exits; a late checkpoint cannot overwrite
            # the terminal state or lose already committed questions.
            latest=self.store.get(job['id'])
            if latest['cancel']:
                self.store.update(job['id'],'cancelled','已取消，已保存结果保留')
            elif self.stop.is_set() and latest['state']=='running':
                self.store.update(job['id'],'interrupted','服务停止，已保存结果保留，可重试')
            elif latest['state']=='running':
                self.store.update(job['id'],'failed','处理进程异常退出',error=f'worker exit code: {process.exitcode}')
        finally:
            if process.pid is not None:
                if process.is_alive():process.terminate();process.join(timeout=2)
                if not process.is_alive():process.close()
    def cancelled(self,job):
        if self.stop.is_set():
            return True
        current = self.store.get(job['id'])
        return current['cancel'] or current['state'] in ('interrupted', 'cancelled')
    def run(self,job):
        import generate_from_file as generator
        import automatic_question_validator as validator
        import multimodal_reader as reader
        from . import web_question_review
        generator.OLLAMA_URL=validator.OLLAMA_URL=config.OLLAMA_URL
        generator.MODEL_NAME=validator.REVIEW_MODEL=config.TEXT_MODEL
        reader.VISION_MODEL=config.VISION_MODEL
        reader.OLLAMA_CHAT_URL=config.OLLAMA_URL
        reader.VISION_TIMEOUT=validator.REVIEW_TIMEOUT=config.MODEL_TIMEOUT
        generator.AUDIT=validator.AUDIT=reader.AUDIT=lambda phase,response:self.store.record_call(job['id'],phase,response)
        accepted=[];rejected=[];reports=[{'name':'上传资料','status':'error','error':str(w)[:300]} for w in job['request'].get('uploadWarnings',[])];parts=0;start=time.monotonic();auto_points=not job['request']['points']
        model_only=job['request'].get('requireModelGeneration',False)
        practice_plan = self.store.practice_plan(job) if model_only and hasattr(self.store, 'practice_plan') else PracticePlan()
        practice_context = practice_plan.instructions()
        history_evidence = practice_plan.evidence
        retry_budget=1
        def checkpoint(stage):
            self.store.update(job['id'],'running',stage,result_bundle(self.store.service_id,job,accepted,rejected,reports))
        for ident in job['request']['fileIds']:
            source=self.store.file(ident,job['owner'])
            if self.cancelled(job):break
            if len(accepted)>=job['request']['questionCount']:
                reports.append({'fileId':ident,'name':source['name'],'status':'not_processed_target_reached'});continue
            if time.monotonic()-start>1800:
                reports.append({'fileId':ident,'name':source['name'],'status':'error','error':'已超过任务处理预算'});break
            report={'fileId':ident,'name':source['name'],'status':'parsing','partsProcessed':0};reports.append(report)
            checkpoint('解析 '+source['name'])
            try:
                validate_file(Path(source['path']),source['name'])
                report['parsing']=[]
                sections=reader.iter_automatic_sections(Path(source['path']),self.store.root/'ocr_cache',checkpoint,vision_fallback=job['request'].get('visionFallback',False))
                file_parts=0
                for section in sections:
                    if self.cancelled(job) or len(accepted)>=job['request']['questionCount']:break
                    report['parsing'].append({**{k:section.get(k) for k in ('location','extraction','page','pagesAvailable','pagesLimit','ocrConfidence','ocrLines','lowConfidenceLines','incompleteLines','parsingNote','parsingError')},'textPreview':section['text'][:6000]})
                    if section.get('parsingError') or not section['text'].strip():
                        rejected.append({'sourceFile':source['name'],'sourceLocation':section['location'],'reasons':[section.get('parsingError','没有可用文字')],'status':'text_unreadable'})
                        checkpoint('已保存文字识别结果')
                        continue
                    if section.get('requiresVisual',False) or section['visualAssisted']:
                        rejected.append({'sourceFile':source['name'],'sourceLocation':section['location'],'reasons':['此段仅有未经核实的视觉描述，不能作为文字题的事实依据'],'status':'visual_unverified'})
                        checkpoint('已跳过需人工核对的图文页')
                        continue
                    material=usable_practice_text(section['text']) if model_only else section['text']
                    if model_only and section.get('extraction')=='ocr' and looks_like_ocr_table(material):
                        rejected.append({'sourceFile':source['name'],'sourceLocation':section['location'],
                                         'reasons':['表格识别结果缺少可核对的行列关系，已跳过该表出题'],'status':'text_unreadable'})
                        checkpoint('已跳过缺少行列关系的表格')
                        continue
                    if not material.strip():
                        rejected.append({'sourceFile':source['name'],'sourceLocation':section['location'],'reasons':['此段只有选项或缺少上下文的讲解，缺少可据以出题的正文'],'status':'text_unreadable'})
                        checkpoint('已跳过缺少正文的段落')
                        continue
                    source_parts = split_practice_text(material, generator.MAX_CHARS) if model_only else generator.split_text(material)
                    for part in source_parts:
                        if self.cancelled(job) or len(accepted)>=job['request']['questionCount']:break
                        if file_parts>=config.MAX_PARTS or parts>=12:break
                        if time.monotonic()-start>1800:raise TimeoutError('任务超过 30 分钟预算')
                        file_parts+=1;parts+=1;report['partsProcessed']=file_parts
                        checkpoint(f'生成与复核 {source["name"]} 第{file_parts}段')
                        try:
                            points=job['request']['points']
                            if auto_points and model_only:
                                points=[]  # Each batch proposes labels; only accepted evidence enters the result catalogue.
                            elif auto_points:
                                checkpoint('正在从资料识别知识点')
                                points=derive_points(part,job['request'].get('requirements',''),generator.AUDIT)
                                job['request']['points']=list({p['name']:p for p in job['request']['points']+points}.values())
                                self.store.update_request(job['id'],job['request'])
                            feedback=None
                            bad=[]
                            for attempt in range(2):
                                if self.cancelled(job) or len(accepted)>=job['request']['questionCount']:break
                                if attempt:
                                    if model_only:
                                        if accepted or not bad or not retry_budget:break
                                        retry_budget-=1
                                    checkpoint('根据质检原因重新生成')
                                stage='AI生成题目（同步提取知识点）' if model_only and auto_points else 'AI生成题目'
                                checkpoint(f'{stage} · 等待本机模型 · {source["name"]} 第{file_parts}段')
                                remaining=job['request']['questionCount']-len(accepted)
                                count=min(4,remaining+1) if model_only else min(3,remaining)
                                used_evidence = history_evidence.union(q['explanation'] for q in accepted)
                                created=generator.generate_questions(part,question_count=count,knowledge_points=points,timeout=config.MODEL_TIMEOUT,raw_candidates=True,feedback=feedback,requirements=job['request'].get('requirements',''),difficulty=job['request'].get('difficulty',0),used_evidence=used_evidence,allow_rule_generation=not model_only,compact_source=model_only,practice_context=practice_context)
                                if not created:rejected.append({'sourceFile':source['name'],'reasons':[EXHAUSTED if practice_context else '本段没有新的、证据充分的可用题目']})
                                for q in created:
                                    if isinstance(q,dict):
                                        if model_only and auto_points:
                                            try:q['knowledgePoint']=Point(name=q.get('knowledgePoint'),summary=q['explanation']).name
                                            except (KeyError,ValueError):q['mappingError']=True
                                        elif q.get('knowledgePoint') not in [p['name'] for p in points]:q['mappingError']=True
                                    if isinstance(q,dict) and job['request'].get('difficulty',0) and q.get('difficulty')!=['','简单','中等','困难'][job['request']['difficulty']]:q['difficultyError']=True
                                report['generatedCandidates']=report.get('generatedCandidates',0)+len(created)
                                checkpoint(f'自动质量初筛 · {source["name"]} 第{file_parts}段')
                                if model_only:
                                    passed,bad=web_question_review.validate_questions(
                                        created,part,accepted,practice_plan,
                                        lambda: checkpoint('自动质量初筛 · 等待本机模型独立复核'))
                                else:
                                    passed,bad=validator.validate_questions(created,part,accepted)
                                for q in passed:
                                    q.update(sourceFile=source['name'],sourceFileId=ident,sourceHash=source['sha256'],sourceLocation=section['location'],generationModel=q.get('generationModel',config.TEXT_MODEL),visualAssisted=section['visualAssisted'])
                                    q.update(extraction=section.get('extraction','text'),ocrConfidence=section.get('ocrConfidence'),textOnly=True)
                                    if section.get('requiresVisual',False) or section['visualAssisted']:
                                        rejected.append({'question':q,'reasons':['依赖图片或视觉观察，需对照原图验证；未自动导入'],'status':'visual_unverified'})
                                    elif len(accepted)<job['request']['questionCount']:
                                        accepted.append(q)
                                        if model_only and auto_points and not any(p['name']==q['knowledgePoint'] for p in job['request']['points']):
                                            job['request']['points'].append({'name':q['knowledgePoint'],'summary':q['evidenceQuote']})
                                for row in bad:row.update(sourceFile=source['name'],sourceLocation=section['location'],generationAttempt=attempt+1)
                                rejected.extend(bad)
                                if passed:checkpoint(f'初筛通过 · 已有 {len(accepted)} 道题可练习')
                                feedback=json.dumps([{'reasons':row['reasons']} for row in bad[:3]],ensure_ascii=False)[:1000]
                                if section.get('requiresVisual',False) or section['visualAssisted']:break
                        except Timeout:
                            rejected.append({'sourceFile':source['name'],'sourceLocation':section['location'],
                                             'reasons':['等待本机模型响应超时，请稍后重试。']})
                        except Exception as exc:rejected.append({'sourceFile':source['name'],'sourceLocation':section['location'],'reasons':[f'本段处理失败：{exc}']})
                        checkpoint('已保存分段结果')
                    if len(accepted)>=job['request']['questionCount'] or file_parts>=config.MAX_PARTS or parts>=12:break
                if not report['parsing']:raise ValueError('资料没有可识别内容')
                report.update(status='processed_with_limits',limits={'pdfPages':5,'partsPerFile':config.MAX_PARTS,'totalParts':12},sectionsProcessed=len(report['parsing']))
            except Exception as exc:report.update(status='error',error=str(exc)[:500])
            checkpoint('已保存文件结果')
        result=result_bundle(self.store.service_id,job,accepted,rejected,reports)
        state='cancelled' if self.cancelled(job) else ('partial' if accepted and (len(accepted)<job['request']['questionCount'] or any(f['status']=='error' for f in reports)) else 'succeeded' if accepted else 'failed')
        reasons = {reason for row in rejected for reason in row.get('reasons', [])}
        exhausted = bool(reasons) and reasons <= {EXHAUSTED, REPEATED}
        error = '' if accepted or state=='cancelled' else EXHAUSTED if exhausted else '没有可导入题目，请查看文件与质检原因'
        self.store.update(job['id'],state,'已结束',result,error=error)
