"""Loopback-only Web adapter. Existing Android bearer-auth API remains unchanged."""
from contextlib import asynccontextmanager
from pathlib import Path
import hashlib
import json
import os
import re
import time
import uuid
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import config
from . import exam_practice
from .content_exporter import result_bundle
from .file_storage import validate_file
from .model_status import generation_readiness
from .practice_quality import standalone_issue
from .schemas import JobRequest
from .worker import Runner
from .web_content import OWNER, WebStore, archive_questions, candidates, eligible, is_library_deleted, questions, removed_items, visible_questions
from . import web_practice

DEFAULT_LIBRARIES = {'sql':'SQL 学习笔记','structure':'数据结构','english':'英语六级','reasoning':'行测资料分析'}
ItemKind = Literal['source','set','question','task']
ROOT = Path(os.getenv('AI_WEB_DATA_DIR', str(config.ROOT / 'runtime' / 'web'))).resolve()
store = WebStore(ROOT)
runner = Runner(store)

def init_web_tables():
    with store.db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS web_libraries(id TEXT PRIMARY KEY,title TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS web_deleted_libraries(library_id TEXT PRIMARY KEY,deleted REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS web_removed_items(library_id TEXT NOT NULL,kind TEXT NOT NULL,item_id TEXT NOT NULL,
            label TEXT NOT NULL,removed REAL NOT NULL,PRIMARY KEY(library_id,kind,item_id));
        CREATE TABLE IF NOT EXISTS web_tasks(task_id TEXT PRIMARY KEY,library_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS web_task_retries(original_id TEXT PRIMARY KEY,retry_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS web_questions(question_id TEXT NOT NULL,library_id TEXT NOT NULL,task_id TEXT NOT NULL,payload TEXT NOT NULL,saved REAL NOT NULL,PRIMARY KEY(library_id,question_id));
        ''')
        web_practice.init_tables(db)
init_web_tables()

@asynccontextmanager
async def lifespan(app):
    store.archive_previous_results()
    runner.start()
    try:
        yield
    finally:
        runner.close()

app = FastAPI(title='知学伴本机 Web 出题接口',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
ALLOWED_ORIGINS = {f'http://{host}:{port}' for host in ('127.0.0.1','localhost') for port in (5173,4173,8091)}

@app.middleware('http')
async def local_browser_boundary(request: Request, call_next):
    origin=request.headers.get('origin')
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({'detail':'只允许本机知学伴页面访问'},status_code=403)
    return await call_next(request)

def task(ident):
    job=store.get(ident,OWNER)
    with store.db() as db:
        link=db.execute('SELECT library_id FROM web_tasks WHERE task_id=?',(ident,)).fetchone()
    if not job or not link: raise HTTPException(404,'生成任务不存在')
    return job,link['library_id']

def stage_code(stage):
    if stage.startswith(('AI生成', '根据质检原因重新生成')): return 'generation'
    if stage.startswith(('自动质量初筛', '初筛通过')): return 'quality'
    if stage.startswith('正在从资料识别知识点'): return 'knowledge'
    return 'parsing'

def task_view(job, library_id):
    with store.db() as db:
        events=[dict(row) for row in db.execute('SELECT stage,state,created FROM job_events WHERE job_id=? ORDER BY id',(job['id'],))]
        saved_ids={row['question_id'] for row in db.execute('SELECT question_id FROM web_questions WHERE library_id=?',(library_id,))}
        archived=is_library_deleted(db,library_id)
        removed=removed_items(db,library_id)
        library=db.execute('SELECT title FROM web_libraries WHERE id=?',(library_id,)).fetchone()
    for event in events: event['stageCode']=stage_code(event['stage'])
    # End/checkpoint labels are not invented phases or percentages.
    phase_events=[event for event in events if any(word in event['stage'] for word in ('解析 ','提取文字','识别扫描','识别图片','识别 Word','知识点','AI生成','初筛','重新生成'))]
    issues=job['result'].get('rejected',[])
    file_errors=[f.get('error') for f in job['result'].get('files',[]) if f.get('error')]
    reasons=[str(reason) for issue in issues for reason in issue.get('reasons',[])]
    error='；'.join([job['error']]+file_errors+reasons[:5]).strip('；') if job['state'] in ('failed','interrupted','cancelled') else ''
    available=[] if archived else visible_questions(job,library_id,removed)
    exam_topic=job['request'].get('examTopic')
    exam_info={'topic':exam_topic,'label':exam_practice.TOPICS[exam_topic][0] if exam_topic!='mixed' else '综合计算',
               'reference':exam_practice.REFERENCE} if exam_topic else None
    return {'taskId':job['id'],'status':job['state'],'stage':job['stage'],
            'stageCode':phase_events[-1]['stageCode'] if phase_events else 'parsing',
            'events':phase_events,'generatedQuestionCount':len(candidates(job)) if exam_info else sum(f.get('generatedCandidates',0) for f in job['result'].get('files',[])),
            'acceptedQuestionCount':len(available),'requestedQuestionCount':job['request']['questionCount'],
            'availableQuestions':available,
            'examPractice':exam_info,
            'libraryDeleted':archived,
            'removedSet':('set',job['id']) in removed,
            'removedQuestionCount':sum(('question',item['id']) in removed for item in questions(job,library_id)),
            'filteredQuestionCount':sum(bool(standalone_issue(item.get('prompt'),item.get('explanation'),item.get('options'))) for item in candidates(job)),
            'savedQuestionCount':sum(item['id'] in saved_ids for item in available),
            'error':error,'resultId':job['id'] if job['state'] not in ('queued','running') else None,
            'libraryId':library_id,'libraryName':library['title'] if library else job['request'].get('libraryName',library_id),'files':job['result'].get('files',[]),'rejected':issues,
            'reviewNote':job['result'].get('reviewNote',''),'created':job['created'],'updated':job['updated']}

class LibraryInput(BaseModel):
    title: str = Field(min_length=1,max_length=120)

class ExamPracticeInput(BaseModel):
    libraryId: str
    libraryName: str = Field(min_length=1,max_length=120)
    questionCount: int = Field(default=5,ge=1,le=12)
    topic: Literal['mixed','complement','overflow','floating','graph','cache'] = 'mixed'

def check_library_id(ident):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',ident): raise HTTPException(422,'知识库ID格式无效')

def require_active_library(db,ident):
    if is_library_deleted(db,ident):
        raise HTTPException(409,'知识库已移入回收站，请先恢复知识库')

def write_library(db,ident,title):
    check_library_id(ident)
    title=title.strip()
    if not title: raise HTTPException(422,'知识库名称不能为空')
    require_active_library(db,ident)
    db.execute('INSERT INTO web_libraries VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title',(ident,title,time.time()))

def put_library(ident,title):
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        write_library(db,ident,title)

def resolve_library(db,ident,title,now):
    check_library_id(ident)
    require_active_library(db,ident)
    title=title.strip()
    if not title: raise HTTPException(422,'知识库名称不能为空')
    db.execute('INSERT OR IGNORE INTO web_libraries VALUES(?,?,?)',(ident,title,now))
    return db.execute('SELECT title FROM web_libraries WHERE id=?',(ident,)).fetchone()['title']

@app.get('/api/health')
def health():
    return {'service':'zhixue-web-local','textModel':config.TEXT_MODEL,'visionModel':config.VISION_MODEL,**generation_readiness()}

@app.put('/api/libraries/{ident}')
def upsert_library(ident: str, value: LibraryInput):
    put_library(ident,value.title)
    return {'id':ident,'title':value.title.strip()}

@app.delete('/api/libraries/{ident}')
def delete_library(ident: str):
    check_library_id(ident)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        if is_library_deleted(db,ident):return {'id':ident}
        if db.execute("""SELECT 1 FROM web_tasks AS task JOIN jobs AS job ON job.id=task.task_id
            WHERE task.library_id=? AND job.owner=? AND job.state IN ('queued','running') LIMIT 1""",(ident,OWNER)).fetchone():
            raise HTTPException(409,'此知识库还有出题任务正在排队或生成，请在任务结束后删除')
        if not db.execute('SELECT 1 FROM web_libraries WHERE id=?',(ident,)).fetchone():
            if ident not in DEFAULT_LIBRARIES: raise HTTPException(404,'知识库不存在')
            write_library(db,ident,DEFAULT_LIBRARIES[ident])
        db.execute('INSERT INTO web_deleted_libraries VALUES(?,?)',(ident,time.time()))
    return {'id':ident}

@app.post('/api/libraries/{ident}/restore')
def restore_library(ident: str):
    check_library_id(ident)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM web_libraries WHERE id=?',(ident,)).fetchone():
            raise HTTPException(404,'知识库不存在')
        db.execute('DELETE FROM web_deleted_libraries WHERE library_id=?',(ident,))
    return {'id':ident}

def item_label(db,library_id,kind,ident):
    if kind=='source':
        row=db.execute("""SELECT f.name,MAX(j.state IN ('queued','running')) AS busy
            FROM web_tasks AS t JOIN jobs AS j ON j.id=t.task_id
            JOIN json_each(j.request,'$.fileIds') AS ids JOIN files AS f ON f.id=ids.value
            WHERE t.library_id=? AND f.id=? AND j.owner=? AND f.owner=? GROUP BY f.id""",(library_id,ident,OWNER,OWNER)).fetchone()
        if row and row['busy']:raise HTTPException(409,'这份资料正在用于出题，请在任务结束后移除')
        return row['name'] if row else None
    if kind=='task':
        row=db.execute('''SELECT j.state FROM web_tasks AS t JOIN jobs AS j ON j.id=t.task_id
            WHERE t.library_id=? AND j.id=? AND j.owner=?''',(library_id,ident,OWNER)).fetchone()
        if row and row['state'] in ('queued','running'):raise HTTPException(409,'任务仍在运行，可先取消任务')
        return f'出题任务 {ident[:8]}' if row else None
    if kind=='set':
        row=db.execute('SELECT 1 FROM web_questions WHERE library_id=? AND task_id=? LIMIT 1',(library_id,ident)).fetchone()
        return f'AI 题目集 {ident[:8]}' if row else None
    row=db.execute('SELECT payload FROM web_questions WHERE library_id=? AND question_id=?',(library_id,ident)).fetchone()
    return json.loads(row['payload'])['prompt'] if row else None

@app.delete('/api/libraries/{library_id}/items/{kind}/{ident}')
def remove_item(library_id: str, kind: ItemKind, ident: str):
    check_library_id(library_id)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_library(db,library_id)
        label=item_label(db,library_id,kind,ident)
        if label is None:raise HTTPException(404,'找不到此内容')
        db.execute('INSERT OR IGNORE INTO web_removed_items VALUES(?,?,?,?,?)',(library_id,kind,ident,label,time.time()))
    return {'id':ident}

@app.post('/api/libraries/{library_id}/items/{kind}/{ident}/restore')
def restore_item(library_id: str, kind: ItemKind, ident: str):
    check_library_id(library_id)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_library(db,library_id)
        db.execute('DELETE FROM web_removed_items WHERE library_id=? AND kind=? AND item_id=?',(library_id,kind,ident))
    return {'id':ident}

@app.get('/api/libraries')
def libraries():
    with store.db() as db:
        result=[]
        deleted=[dict(row) for row in db.execute('''SELECT lib.id,lib.title FROM web_libraries AS lib
            JOIN web_deleted_libraries AS trash ON trash.library_id=lib.id ORDER BY trash.deleted DESC''')]
        removed=[dict(row) for row in db.execute('''SELECT i.library_id AS libraryId,i.kind,i.item_id AS id,i.label,l.title AS libraryName
            FROM web_removed_items AS i JOIN web_libraries AS l ON l.id=i.library_id
            WHERE l.id NOT IN (SELECT library_id FROM web_deleted_libraries) ORDER BY i.removed DESC''')]
        for library in db.execute('''SELECT id,title FROM web_libraries WHERE id NOT IN
            (SELECT library_id FROM web_deleted_libraries) ORDER BY created'''):
            sets={}
            hidden=removed_items(db,library['id'])
            sources={};points=set()
            for link in db.execute('SELECT task_id FROM web_tasks WHERE library_id=?',(library['id'],)):
                job=store.get(link['task_id'],OWNER)
                if not job: continue
                for file_id in job['request'].get('fileIds',[]):
                    if ('source',file_id) in hidden:continue
                    source=store.file(file_id,OWNER)
                    if source: sources[file_id]={'id':file_id,'name':source['name'],'size':source['size']}
            for row in db.execute('SELECT task_id,payload FROM web_questions WHERE library_id=? ORDER BY saved DESC',(library['id'],)):
                item=json.loads(row['payload'])
                if ('set',row['task_id']) in hidden or ('question',item.get('id')) in hidden or not eligible(item):continue
                points.update(item['points'])
                ident=row['task_id']
                question_set=sets.setdefault(ident,{'id':ident,'taskId':ident,'count':0,
                    'examPractice':item['ai'].get('reviewMethod')==exam_practice.METHOD})
                question_set['count']+=1
            result.append(dict(library,questionSets=list(sets.values()),sources=list(sources.values()),points=sorted(points)))
    return {'libraries':result,'deletedLibraries':deleted,'removedItems':removed}

@app.get('/api/generation-tasks')
def recent_tasks():
    with store.db() as db:
        rows=db.execute('''SELECT j.id AS taskId,j.state AS status,j.stage,j.created,t.library_id AS libraryId,
            COALESCE(l.title,json_extract(j.request,'$.libraryName'),t.library_id) AS libraryName
            FROM jobs AS j JOIN web_tasks AS t ON t.task_id=j.id
            LEFT JOIN web_libraries AS l ON l.id=t.library_id
            WHERE j.owner=? AND t.library_id NOT IN (SELECT library_id FROM web_deleted_libraries)
            AND NOT EXISTS (SELECT 1 FROM web_removed_items WHERE library_id=t.library_id AND kind='task' AND item_id=j.id)
            ORDER BY CASE WHEN j.state IN ('queued','running') THEN 0 ELSE 1 END,j.created DESC LIMIT 30''',(OWNER,))
        return {'tasks':[dict(row) for row in rows]}

@app.post('/api/exam-practice-tasks',status_code=201)
def create_exam_practice(value: ExamPracticeInput):
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        return insert_exam_practice(db, store, value)


def insert_exam_practice(db, target_store, value):
    ident=uuid.uuid4().hex
    start=time.time()
    accepted,points=exam_practice.generate(value.questionCount,value.topic,ident)
    title=resolve_library(db,value.libraryId,value.libraryName,start)
    request={'fileIds':[],'libraryName':title,'subject':'软件设计师计算专项','points':points,
             'questionCount':value.questionCount,'examTopic':value.topic}
    job={'id':ident,'owner':OWNER,'request':request}
    result=result_bundle(target_store.service_id,job,accepted,[],[])
    result['reviewNote']='按软件设计师公开考试范围编写的原创模拟题。题干参数、唯一答案与逐步解析由程序计算。'
    db.execute('''INSERT INTO jobs(id,owner,state,stage,request,result,error,created,updated)
        VALUES(?,?,'succeeded','专项题已生成',?,?,'',?,?)''',(ident,OWNER,json.dumps(request,ensure_ascii=False),
            json.dumps(result,ensure_ascii=False),start,time.time()))
    db.execute('INSERT INTO web_tasks VALUES(?,?)',(ident,value.libraryId))
    target_store.publish_result(db, ident, 'succeeded', result, start)
    return {'taskId':ident,'status':'succeeded'}

@app.post('/api/generation-tasks',status_code=202)
def create_task(files: list[UploadFile]=File(...),requirements: str=Form(''),libraryId: str=Form(...),
                libraryName: str=Form(...),questionCount: int=Form(3,ge=1,le=12),questionType: str=Form('single_choice')):
    if questionType!='single_choice': raise HTTPException(422,'当前仅支持四选一单选题')
    if not 1<=len(files)<=config.MAX_FILES: raise HTTPException(422,'每次选择1–5份资料')
    check_library_id(libraryId)
    with store.db() as db:require_active_library(db,libraryId)
    try:
        parsed=JobRequest(fileIds=['pending'],libraryName=libraryName,subject='资料学习',questionCount=questionCount,
                          requirements=requirements,requireModelGeneration=True,visionFallback=True)
    except ValidationError as exc:
        message='；'.join(error['msg'].removeprefix('Value error, ') for error in exc.errors())
        raise HTTPException(422,message)
    readiness=generation_readiness()
    if not readiness['generationReady']:
        issue=readiness['generationIssue'].replace('已上传的资料会保留。','当前尚未创建任务，请保留文件选择并在恢复服务后重试。').replace('资料已保留，','本次尚未创建任务，')
        raise HTTPException(503,issue)
    written=[]; metadata=[]; committed=False
    try:
        for upload in files:
            name=Path((upload.filename or 'file').replace('\\','/')).name
            path=store.root/'uploads'/(uuid.uuid4().hex+Path(name).suffix.lower())
            written.append(path); digest=hashlib.sha256(); size=0
            with path.open('wb') as out:
                while chunk:=upload.file.read(65536):
                    size+=len(chunk)
                    if size>config.MAX_FILE_BYTES: raise ValueError(f'{name} 超过20MB')
                    digest.update(chunk);out.write(chunk)
            try: validate_file(path,name)
            except Exception as exc: raise ValueError(f'{name}：{exc}') from exc
            metadata.append((uuid.uuid4().hex,OWNER,name,digest.hexdigest(),size,str(path)))
        parsed.fileIds=[item[0] for item in metadata]
        ident=uuid.uuid4().hex;now=time.time()
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            parsed.libraryName=resolve_library(db,libraryId,parsed.libraryName,now)
            db.executemany('INSERT INTO files VALUES(?,?,?,?,?,?)',metadata)
            db.execute("INSERT INTO jobs(id,owner,state,stage,request,result,error,created,updated) VALUES(?,?,'queued','等待处理',?,'{}','',?,?)",(ident,OWNER,json.dumps(parsed.model_dump(),ensure_ascii=False),now,now))
            db.execute('INSERT INTO web_tasks VALUES(?,?)',(ident,libraryId))
        committed=True
        return {'taskId':ident,'status':'queued'}
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    finally:
        if not committed:
            for path in written: path.unlink(missing_ok=True)
        for upload in files: upload.file.close()

@app.get('/api/generation-tasks/{ident}')
def get_task(ident: str):
    job,library_id=task(ident)
    return task_view(job,library_id)

@app.get('/api/generation-tasks/{ident}/questions')
def get_questions(ident: str):
    job,library_id=task(ident)
    if job['state'] in ('queued','running'): raise HTTPException(409,'任务仍在运行')
    with store.db() as db:
        require_active_library(db,library_id)
        available=visible_questions(job,library_id,removed_items(db,library_id))
    return {'taskId':ident,'questions':available,'rejected':job['result'].get('rejected',[])}

@app.post('/api/generation-tasks/{ident}/save')
def save_questions(ident: str):
    job,library_id=task(ident)
    if job['state'] not in ('succeeded','partial'): raise HTTPException(409,'仅完成或部分完成任务的合格题目可以入库')
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_library(db,library_id)
        count=archive_questions(db, job, library_id, time.time(), removed_items(db,library_id))
        if not count: raise HTTPException(409,'没有可保存的题目，请检查初筛结果或回收站')
    return {'libraryId':library_id,'saved':count}

@app.post('/api/generation-tasks/{ident}/practice-sessions')
def complete_practice(ident: str, submission: web_practice.Submission):
    job,library_id=task(ident)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_library(db,library_id)
        available=visible_questions(job,library_id,removed_items(db,library_id))
        return web_practice.save_session(db,submission,ident,library_id,available,time.time())

@app.get('/api/practice-history')
def practice_history(libraryId: str | None = None):
    with store.db() as db:
        if libraryId is not None:
            check_library_id(libraryId)
            require_active_library(db,libraryId)
        return web_practice.history(db,libraryId)

@app.post('/api/generation-tasks/{ident}/cancel')
def cancel_task(ident: str):
    task(ident)
    store.cancel(ident,OWNER)
    return {'taskId':ident}

@app.post('/api/generation-tasks/{ident}/retry',status_code=202)
def retry(ident: str):
    job, library_id = task(ident)
    if job['state'] in ('queued', 'running'):
        raise HTTPException(409, '任务仍在执行')
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_library(db, library_id)
        existing = db.execute('''SELECT j.id, j.state FROM web_task_retries r JOIN jobs j ON j.id=r.retry_id
                                 WHERE r.original_id=?''', (ident,)).fetchone()
        if existing:
            return {'taskId': existing['id'], 'status': existing['state']}

        request = {**job['request'], 'points': []}
        if request.get('examTopic'):
            response = insert_exam_practice(db, store, ExamPracticeInput(
                libraryId=library_id, libraryName=request['libraryName'],
                questionCount=request['questionCount'], topic=request['examTopic']))
        else:
            removed = removed_items(db, library_id)
            if any(('source', file_id) in removed for file_id in request.get('fileIds', [])):
                raise HTTPException(409, '任务的原始资料已移入回收站，请恢复资料后重试')
            new = uuid.uuid4().hex
            now = time.time()
            db.execute("""INSERT INTO jobs(id,owner,state,stage,request,result,error,created,updated)
                          VALUES(?,?,'queued','等待处理',?,'{}','',?,?)""",
                       (new, OWNER, json.dumps(request, ensure_ascii=False), now, now))
            db.execute('INSERT INTO web_tasks VALUES(?,?)', (new, library_id))
            response = {'taskId': new, 'status': 'queued'}
        db.execute('INSERT INTO web_task_retries VALUES(?,?)', (ident, response['taskId']))
        return response
