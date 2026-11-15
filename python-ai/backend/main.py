from contextlib import asynccontextmanager
import hashlib
import os
import uuid
from pathlib import Path
import requests
from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from . import config
from .file_storage import validate_file
from .job_store import Store
from .schemas import JobRequest
from .worker import Runner
from .model_status import generation_readiness

store = Store()
runner = Runner(store)


@asynccontextmanager
async def lifespan(app):
    runner.start()
    try:
        yield
    finally:
        runner.close()


app = FastAPI(title='知学伴 AI 资料出题服务', lifespan=lifespan)


def identity(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, '请先登录')
    try:
        response = requests.get(
            config.AUTH_URL + '/api/auth/me',
            headers={'Authorization': authorization},
            timeout=(3, 5),
        )
    except requests.RequestException:
        raise HTTPException(503, '账号验证服务暂不可用，原有本机学习不受影响')
    if response.status_code == 401:
        raise HTTPException(401, '登录已失效，请重新登录')
    if response.status_code != 200:
        raise HTTPException(503, '账号验证暂不可用')
    try:
        return response.json()['id']
    except (ValueError, KeyError):
        raise HTTPException(503, '账号服务返回格式异常')


def owned(ident, owner):
    value = store.get(ident, owner)
    if not value:
        raise HTTPException(404, '任务不存在或不属于当前账号')
    return value


def public(job):
    result = job['result']
    return {
        'jobId': job['id'],
        'state': job['state'],
        'stage': job['stage'],
        'error': job['error'],
        'cancelRequested': bool(job['cancel']),
        'accepted': result.get('accepted', 0),
        'files': result.get('files', []),
        'rejected': result.get('rejected', []),
        'updated': job['updated'],
    }


@app.get('/api/ai/health')
def health():
    readiness = generation_readiness()
    return {
        'status': 'ok' if readiness['generationReady'] else 'degraded',
        'service': 'zhixue-ai',
        'serviceId': store.service_id,
        **readiness,
        'modelMetadataOnly': True,
        'maxFileBytes': config.MAX_FILE_BYTES,
    }


def require_generation():
    readiness = generation_readiness()
    if not readiness['generationReady']:
        raise HTTPException(503, readiness['generationIssue'])


@app.post('/api/ai/files')
def upload(files: list[UploadFile], owner=Depends(identity)):
    if not 1 <= len(files) <= config.MAX_FILES:
        raise HTTPException(422, '一次选择 1–5 份资料')
    results = []
    for item in files:
        name = Path((item.filename or 'file').replace('\\', '/')).name
        path = store.root / 'uploads' / (uuid.uuid4().hex + Path(name).suffix.lower())
        try:
            total = 0
            digest = hashlib.sha256()
            with open(path, 'wb') as out:
                while chunk := item.file.read(65536):
                    total += len(chunk)
                    if total > config.MAX_FILE_BYTES:
                        raise ValueError('单文件超过 20 MB')
                    digest.update(chunk)
                    out.write(chunk)
            validate_file(path, name)
            ident = store.add_file(owner, name, digest.hexdigest(), total, path)
            results.append(
                {
                    'fileId': ident,
                    'name': name,
                    'status': 'ready',
                    'sha256': digest.hexdigest(),
                    'size': total,
                }
            )
        except Exception as exc:
            path.unlink(missing_ok=True)
            results.append({'name': name, 'status': 'error', 'error': str(exc)[:300]})
        finally:
            item.file.close()
    return {'files': results}


@app.post('/api/ai/jobs', status_code=202)
def create(request: JobRequest, owner=Depends(identity)):
    if len(set(request.fileIds)) != len(request.fileIds):
        raise HTTPException(422, '文件重复')
    if len({x.name for x in request.points}) != len(request.points):
        raise HTTPException(422, '知识点重复')
    if any(not store.file(x, owner) for x in request.fileIds):
        raise HTTPException(404, '资料不存在或不属于当前账号')
    require_generation()
    return {'jobId': store.create(owner, request.model_dump())}


@app.get('/api/ai/jobs/{ident}')
def status(ident: str, owner=Depends(identity)):
    return public(owned(ident, owner))


@app.get('/api/ai/jobs')
def recent(owner=Depends(identity)):
    return {'jobs': store.recent(owner)}


@app.get('/api/ai/jobs/{ident}/result')
def result(ident: str, owner=Depends(identity)):
    job = owned(ident, owner)
    if job['state'] in ('queued', 'running'):
        raise HTTPException(409, '任务尚未结束')
    return job['result']


@app.post('/api/ai/jobs/{ident}/cancel')
def cancel(ident: str, owner=Depends(identity)):
    job = owned(ident, owner)
    if job['state'] in ('queued', 'running'):
        store.cancel(ident, owner)
    return public(owned(ident, owner))


@app.post('/api/ai/jobs/{ident}/retry', status_code=202)
def retry(ident: str, owner=Depends(identity)):
    job = owned(ident, owner)
    if job['state'] in ('queued', 'running'):
        raise HTTPException(409, '任务仍在处理')
    require_generation()
    return {'jobId': store.create(owner, job['request'])}


@app.get('/api/ai/files/{ident}')
def source(ident: str, owner=Depends(identity)):
    value = store.file(ident, owner)
    if not value:
        raise HTTPException(404, '资料不存在')
    return FileResponse(value['path'], filename=value['name'])
