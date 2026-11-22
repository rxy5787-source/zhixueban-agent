from dataclasses import dataclass
import multiprocessing
import threading
import time
from pathlib import Path
from requests import HTTPError, Timeout
from . import config
from .content_exporter import result_bundle
from .file_storage import validate_file
from .job_store import Store
from .knowledge_extractor import derive_points
from .practice_quality import looks_like_ocr_table, source_units, split_practice_text, usable_practice_text
from .practice_coverage import Scope, make_scopes
from .practice_variety import EXHAUSTED, REPEATED, PracticePlan
from .schemas import Point

@dataclass(frozen=True)
class SourceBatch:
    source: dict
    section: dict
    text: str
    report: dict
    number: int



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
    def source_sections(self, job, ident, read):
        return read()

    def choice_prompt(self, requirement):
        return requirement

    def teaching_issue(self, question, requirement):
        return ''

    def run(self, job):
        import generate_from_file as generator
        import automatic_question_validator as validator
        import multimodal_reader as reader
        from . import web_question_review
        generator.OLLAMA_URL = validator.OLLAMA_URL = config.OLLAMA_URL
        generator.MODEL_NAME = validator.REVIEW_MODEL = config.TEXT_MODEL
        reader.VISION_MODEL = config.VISION_MODEL
        reader.OLLAMA_CHAT_URL = config.OLLAMA_URL
        reader.VISION_TIMEOUT = validator.REVIEW_TIMEOUT = config.MODEL_TIMEOUT
        generator.AUDIT = validator.AUDIT = reader.AUDIT = (
            lambda phase, response: self.store.record_call(job['id'], phase, response))
        request = job['request']
        requirement = request.get('requirements', '')
        model_only = request.get('requireModelGeneration', False)
        auto_points = not request['points']
        history = self.store.practice_plan(job) if model_only and hasattr(self.store, 'practice_plan') else PracticePlan()
        context = history.instructions()
        started = time.monotonic()
        accepted, rejected, batches, coverage = [], [], [], []
        reports = [{'name': '上传资料', 'status': 'error', 'error': str(w)[:300]}
                   for w in request.get('uploadWarnings', [])]

        def result():
            output = result_bundle(self.store.service_id, job, accepted, rejected, reports)
            if coverage:
                output['coverage'] = [row.copy() for row in coverage]
                output['reviewNote'] += ' 考点覆盖：' + '；'.join(
                    f"{row['label']} {row['accepted']}/{row['requested']}" +
                    (f"（{row['reason']}）" if row.get('reason') else '') for row in coverage) + '。'
            return output

        def stopped():
            return self.cancelled(job) or time.monotonic() - started >= 1800

        def checkpoint(stage):
            self.store.update(job['id'], 'running', stage, result())

        for ident in request['fileIds']:
            if stopped():
                break
            source = {**self.store.file(ident, job['owner']), 'id': ident}
            report = {'fileId': ident, 'name': source['name'], 'status': 'parsing',
                      'partsProcessed': 0, 'parsing': []}
            reports.append(report)
            checkpoint('解析 ' + source['name'])
            try:
                validate_file(Path(source['path']), source['name'])
                sections = self.source_sections(job, ident, lambda: reader.iter_automatic_sections(
                    Path(source['path']), self.store.root / 'ocr_cache', checkpoint,
                    vision_fallback=request.get('visionFallback', False)))
                file_batches = []
                for section in sections:
                    if stopped() or len(file_batches) >= config.MAX_PARTS:
                        break
                    report['parsing'].append({
                        **{k: section.get(k) for k in ('location', 'extraction', 'page', 'pagesAvailable',
                           'pagesLimit', 'ocrConfidence', 'ocrLines', 'lowConfidenceLines', 'incompleteLines',
                           'parsingNote', 'parsingError')},
                        'textPreview': section['text'][:6000],
                    })
                    issue, status = '', 'text_unreadable'
                    if section.get('parsingError') or not section['text'].strip():
                        issue = section.get('parsingError') or '没有可用文字'
                    elif section.get('requiresVisual') or section['visualAssisted']:
                        issue, status = '此段只有未经核实的视觉描述，不能用于出题', 'visual_unverified'
                    material = usable_practice_text(section['text']) if model_only else section['text']
                    if not issue and model_only and section.get('extraction') == 'ocr' and looks_like_ocr_table(material):
                        issue = '表格识别结果缺少可核对的行列关系，已跳过该表出题'
                    if not issue and not material.strip():
                        issue = '此段缺少可据以出题的正文'
                    if issue:
                        rejected.append({'sourceFile': source['name'], 'sourceLocation': section['location'],
                                         'reasons': [issue], 'status': status})
                        continue
                    parts = (split_practice_text(material, generator.MAX_CHARS) if model_only
                             else generator.split_text(material))
                    for part in parts:
                        if len(file_batches) >= config.MAX_PARTS:
                            break
                        file_batches.append(SourceBatch(source, section, part, report, len(file_batches) + 1))
                batches.extend(file_batches)
                if not report['parsing']:
                    raise ValueError('资料没有可识别内容')
                report.update(status='processed_with_limits', limits={'pdfPages': 5,
                              'partsPerFile': config.MAX_PARTS, 'totalParts': 12},
                              sectionsProcessed=len(report['parsing']))
            except Exception as exc:
                report.update(status='error', error=str(exc)[:500])

        try:
            if model_only:
                total, scopes = make_scopes(requirement, request['questionCount'], batches, history.weak_points)
                if total != request['questionCount']:
                    request['questionCount'] = total
                    self.store.update_request(job['id'], request)
            else:
                total, scopes = request['questionCount'], [Scope('可用资料', request['questionCount'])]
        except ValueError as exc:
            self.store.update(job['id'], 'failed', '出题计划无法执行', result(), error=str(exc))
            return
        work = [(scope, [(batch, text) for batch in batches if (text := scope.material(batch))])
                for scope in scopes]
        coverage.extend({'label': scope.label, 'requested': scope.quota, 'accepted': 0,
                         'sources': list(dict.fromkeys(batch.source['name'] for batch, _ in inputs)),
                         'reason': '' if inputs else '资料中未找到该考点的可核对原文'}
                        for scope, inputs in work)
        checkpoint('已制定出题覆盖计划')

        def generate(scope, row, batch, part, feedback, attempt):
            remaining = scope.quota - row['accepted']
            label = f'{scope.label} · {batch.source["name"]} 第{batch.number}段'
            report = batch.report
            report['partsProcessed'] += int(attempt == 1)
            used = history.evidence.union(q['evidenceQuote'] for q in accepted)
            if model_only and all(unit in used for unit in source_units(part)):
                return EXHAUSTED
            points = [] if model_only and auto_points else request['points']
            if auto_points and not model_only:
                checkpoint('正在从资料识别知识点')
                points = derive_points(part, requirement, generator.AUDIT)
                request['points'] = list({p['name']: p for p in request['points'] + points}.values())
                self.store.update_request(job['id'], request)
            prompt = (f'本批只考查 {scope.term}，题目和正确选项必须直接考查该考点。'
                      '仅使用下方编号原文及确实支持的事实。' if scope.term else requirement)
            checkpoint(f'AI生成题目 · 等待本机模型 · {label}')
            try:
                created = generator.generate_questions(
                    part, question_count=min(4, remaining + 1) if model_only else min(3, remaining),
                    knowledge_points=points, timeout=config.MODEL_TIMEOUT, raw_candidates=True, feedback=feedback,
                    requirements=self.choice_prompt(prompt) if model_only else prompt,
                    difficulty=request.get('difficulty', 0), used_evidence=used,
                    allow_rule_generation=not model_only, compact_source=model_only, practice_context=context)
            except (Timeout, HTTPError, ValueError, KeyError, TypeError) as exc:
                reason = '等待本机模型响应超时，请稍后重试。' if isinstance(exc, Timeout) else '模型响应失败或结构无效。'
                rejected.append({'sourceFile': batch.source['name'], 'sourceLocation': batch.section['location'],
                                 'reasons': [reason], 'generationAttempt': attempt})
                return reason
            for q in created:
                if not isinstance(q, dict):
                    continue
                if model_only and auto_points:
                    try:
                        q['knowledgePoint'] = Point(name=scope.term or q.get('knowledgePoint'),
                                                    summary=q['explanation']).name
                    except (KeyError, ValueError):
                        q['mappingError'] = True
                elif q.get('knowledgePoint') not in [p['name'] for p in points]:
                    q['mappingError'] = True
                if request.get('difficulty') and q.get('difficulty') != ['', '简单', '中等', '困难'][request['difficulty']]:
                    q['difficultyError'] = True
            report['generatedCandidates'] = report.get('generatedCandidates', 0) + len(created)
            checkpoint(f'自动质量初筛 · {label}')
            if model_only:
                passed, bad = web_question_review.validate_questions(
                    created, part, accepted, history, lambda: checkpoint('自动质量初筛 · 等待本机模型独立复核'))
            else:
                passed, bad = validator.validate_questions(created, part, accepted)
            for q in passed:
                quote = q['evidenceQuote']
                issue = self.teaching_issue(q['question'], requirement) if model_only else ''
                if not scope.match(quote) or not scope.match(q['question'] + ' ' + q['options'][q['answer']]):
                    issue = '题干和正确选项未覆盖指定考点，或原文不能证明该考点'
                if issue:
                    bad.append({'question': q, 'reasons': [issue], 'status': 'rejected_or_needs_review'})
                    continue
                if row['accepted'] >= scope.quota:
                    break
                q.update(sourceFile=batch.source['name'], sourceFileId=batch.source['id'],
                         sourceHash=batch.source['sha256'], sourceLocation=batch.section['location'],
                         generationModel=q.get('generationModel', config.TEXT_MODEL), visualAssisted=False,
                         extraction=batch.section.get('extraction', 'text'),
                         ocrConfidence=batch.section.get('ocrConfidence'), textOnly=True)
                accepted.append(q)
                row['accepted'] += 1
                if model_only and auto_points and not any(p['name'] == q['knowledgePoint'] for p in request['points']):
                    request['points'].append({'name': q['knowledgePoint'], 'summary': quote})
            for rejected_item in bad:
                rejected_item.update(sourceFile=batch.source['name'], sourceLocation=batch.section['location'],
                                     generationAttempt=attempt)
            rejected.extend(bad)
            if passed:
                checkpoint(f'初筛通过 · 已有 {len(accepted)} 道题可练习')
            return '；'.join(reason for item in bad[:3] for reason in item['reasons'])[:800] or (
                EXHAUSTED if not created else '合格题数不足，请使用尚未考过的原文。')

        # Every target gets a first pass before any target can consume the retry budget.
        first_results = []
        attempts = {}
        for index, ((scope, inputs), row) in enumerate(zip(work, coverage)):
            if stopped():
                break
            if not inputs:
                continue
            batch, text = inputs[0]
            feedback = generate(scope, row, batch, text, None, 1)
            attempts[index, batch.source['id'], batch.number] = 1
            first_results.append((index, feedback))

        retry_budget = min(12, max(2, 2 * len(scopes) + (total - 1) // 4))
        for retry in range(retry_budget):
            if stopped():
                break
            pending = [(index, feedback) for index, feedback in first_results
                       if coverage[index]['accepted'] < work[index][0].quota]
            if not pending:
                break
            index, feedback = pending[retry % len(pending)]
            scope, inputs = work[index]
            row = coverage[index]
            used = history.evidence.union(q['evidenceQuote'] for q in accepted)
            # Prefer an unused source passage, then retry the initial passage with critique.
            candidates = [item for item in inputs if
                          attempts.get((index, item[0].source['id'], item[0].number), 0) < 2 and
                          (not model_only or any(unit not in used for unit in source_units(item[1])))]
            if not candidates:
                first_results = [(i, f) for i, f in first_results if i != index]
                continue
            batch, text = min(candidates, key=lambda item: attempts.get(
                (index, item[0].source['id'], item[0].number), 0))
            key = index, batch.source['id'], batch.number
            attempts[key] = attempts.get(key, 0) + 1
            checkpoint(f"重新生成 · {scope.label} 还缺 {scope.quota - row['accepted']} 道")
            feedback = generate(scope, row, batch, text, feedback, 2)
            first_results = [(i, feedback if i == index else f) for i, f in first_results]

        for row in coverage:
            if row['accepted'] < row['requested'] and not row['reason']:
                row['reason'] = '现有原文与复核结果不足以补足题量'
        status = 'cancelled' if self.cancelled(job) else (
            ('partial' if len(accepted) < total or any(f['status'] == 'error' for f in reports) else 'succeeded')
            if accepted else 'failed')
        reasons = {reason for row in rejected for reason in row.get('reasons', [])}
        exhausted = bool(reasons) and reasons <= {EXHAUSTED, REPEATED}
        missing = '；'.join(f"{row['label']}：{row['reason']}" for row in coverage if row['reason'])
        error = '' if accepted or status == 'cancelled' else (
            EXHAUSTED if exhausted else '没有可导入题目。' + missing)
        self.store.update(job['id'], status, '已结束', result(), error=error)
