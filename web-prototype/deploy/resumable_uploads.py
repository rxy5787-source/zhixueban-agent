"""Persist acknowledged upload offsets before creating the existing generation job."""

from contextlib import ExitStack
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
import time

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from . import study_chat, web_api, web_submissions
from .file_storage import SUPPORTED
from .schemas import JobRequest


router = APIRouter(prefix='/api/resumable-uploads')
CHUNK_BYTES = 256 * 1024
completion_lock = threading.Lock()


class SourceFile(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, le=20 * 1024 * 1024)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class UploadPlan(BaseModel):
    files: list[SourceFile] = Field(min_length=1, max_length=5)
    libraryId: str = Field(min_length=1, max_length=100)
    libraryName: str = Field(min_length=1, max_length=120)
    requirements: str = Field(default='', max_length=1200)
    questionCount: int = Field(ge=1, le=12)
    questionType: str = 'single_choice'


def init_tables(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS web_uploads(
            id TEXT PRIMARY KEY, plan TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS web_upload_offsets(
            upload_id TEXT NOT NULL, file_index INTEGER NOT NULL, received INTEGER NOT NULL,
            PRIMARY KEY(upload_id,file_index));
    ''')


def checked_id(ident):
    if not re.fullmatch(r'[a-f0-9]{32}', ident):
        raise HTTPException(422, '上传标识格式无效')


def part_path(store, ident, index):
    return store.root / 'resumable' / f'{ident}-{index}.part'


def load_plan(db, ident):
    row = db.execute('SELECT plan FROM web_uploads WHERE id=?', (ident,)).fetchone()
    if row is None:
        raise HTTPException(404, '未找到这次上传，请重新提交')
    return json.loads(row['plan'])


def view(db, ident):
    plan = load_plan(db, ident)
    offsets = [row['received'] for row in db.execute(
        'SELECT received FROM web_upload_offsets WHERE upload_id=? ORDER BY file_index', (ident,))]
    return {'uploadId': ident, 'offsets': offsets, 'chunkBytes': CHUNK_BYTES,
            'receipt': web_submissions.find(db, ident), 'files': plan['files']}


@router.put('/{ident}')
def begin(ident: str, plan: UploadPlan):
    checked_id(ident)
    web_api.check_library_id(plan.libraryId)
    if plan.questionType != 'single_choice' and plan.questionType not in study_chat.STUDY_TYPES:
        raise HTTPException(422, '当前支持选择题、记忆口诀、填空和资料问答。')
    try:
        JobRequest(fileIds=['pending'], libraryName=plan.libraryName, subject='资料学习',
                   questionCount=plan.questionCount,
                   requirements=plan.requirements if plan.questionType == 'single_choice' else '')
    except ValidationError:
        raise HTTPException(422, '出题要求不符合当前四选一单选题支持范围')
    if sum(file.size for file in plan.files) > 25 * 1024 * 1024:
        raise HTTPException(413, '单次资料总大小不能超过 25 MiB')
    if any(Path(file.name).suffix.lower() not in SUPPORTED for file in plan.files):
        raise HTTPException(422, '请选择 PDF、DOCX、图片或 TXT')
    store = web_api.request_store()
    payload = json.dumps(plan.model_dump(), ensure_ascii=False, sort_keys=True)
    stale_paths = []
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT plan FROM web_uploads WHERE id=?', (ident,)).fetchone()
        if existing:
            if existing['plan'] != payload:
                raise HTTPException(409, '资料或出题要求与上次不同，请重新提交')
            return view(db, ident)
        web_api.require_active_library(db, plan.libraryId)
        store.check_submission(db)
        expired = list(db.execute('''SELECT id,plan FROM web_uploads u WHERE updated<?
            AND NOT EXISTS(SELECT 1 FROM web_submissions s WHERE s.request_id=u.id)''', (time.time() - 86400,)))
        for row in expired:
            for index in range(len(json.loads(row['plan'])['files'])):
                stale_paths.append(part_path(store, row['id'], index))
            db.execute('DELETE FROM web_upload_offsets WHERE upload_id=?', (row['id'],))
            db.execute('DELETE FROM web_uploads WHERE id=?', (row['id'],))
        pending = db.execute('''SELECT COUNT(*) FROM web_uploads u
            WHERE NOT EXISTS(SELECT 1 FROM web_submissions s WHERE s.request_id=u.id)''').fetchone()[0]
        if pending >= 4:
            raise HTTPException(429, '未完成的上传过多，请先继续已有上传')
        (store.root / 'resumable').mkdir(exist_ok=True)
        now = time.time()
        db.execute('INSERT INTO web_uploads VALUES(?,?,?,?)', (ident, payload, now, now))
        db.executemany('INSERT INTO web_upload_offsets VALUES(?,?,0)', [(ident, i) for i in range(len(plan.files))])
        result = view(db, ident)
    for path in stale_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).warning('Could not remove an expired upload fragment')
    return result


@router.get('/{ident}')
def status(ident: str):
    checked_id(ident)
    with web_api.request_store().db() as db:
        return view(db, ident)


def save_chunk(store, ident, index, offset, content, digest):
    checked_id(ident)
    if not content or len(content) > CHUNK_BYTES or hashlib.sha256(content).hexdigest() != digest:
        raise HTTPException(422, '上传片段校验失败，请重试')
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        plan = load_plan(db, ident)
        if not 0 <= index < len(plan['files']) or offset < 0:
            raise HTTPException(422, '上传位置无效')
        size = plan['files'][index]['size']
        row = db.execute('SELECT received FROM web_upload_offsets WHERE upload_id=? AND file_index=?', (ident, index)).fetchone()
        received = row['received']
        if web_submissions.find(db, ident):
            return {'offset': size}
        if offset + len(content) > size or offset > received:
            raise HTTPException(409, '上传位置不一致，请重新核对进度')
        path = part_path(store, ident, index)
        with path.open('r+b' if path.exists() else 'w+b') as target:
            target.seek(0, 2)
            if target.tell() < received:
                raise HTTPException(409, '已保存片段损坏，请重新上传')
            target.truncate(received)  # Discard a tail left by an interrupted database transaction.
            if offset < received:
                target.seek(offset)
                if offset + len(content) > received or target.read(len(content)) != content:
                    raise HTTPException(409, '重复片段内容不一致')
            else:
                target.seek(received)
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
                received += len(content)
                db.execute('UPDATE web_upload_offsets SET received=? WHERE upload_id=? AND file_index=?', (received, ident, index))
        db.execute('UPDATE web_uploads SET updated=? WHERE id=?', (time.time(), ident))
        return {'offset': received}


@router.put('/{ident}/files/{index}')
async def chunk(ident: str, index: int, offset: int, request: Request):
    content = await request.body()
    return await run_in_threadpool(save_chunk, web_api.request_store(), ident, index, offset, content,
                                   request.headers.get('x-chunk-sha256', ''))


@router.post('/{ident}/complete')
def complete(ident: str):
    checked_id(ident)
    store = web_api.request_store()
    with completion_lock:
        with store.db() as db:
            plan = load_plan(db, ident)
            receipt = web_submissions.find(db, ident)
            offsets = view(db, ident)['offsets']
        if receipt is None:
            if offsets != [file['size'] for file in plan['files']]:
                raise HTTPException(409, '资料尚未上传完整，将继续接收已保存位置之后的内容')
            with ExitStack() as stack:
                uploads = []
                for index, file in enumerate(plan['files']):
                    source = stack.enter_context(part_path(store, ident, index).open('rb'))
                    if hashlib.file_digest(source, 'sha256').hexdigest() != file['sha256']:
                        raise HTTPException(422, '文件完整性校验失败，请重新选择资料')
                    source.seek(0)
                    uploads.append(UploadFile(file=source, filename=file['name']))
                receipt = web_api.create_task(files=uploads, requirements=plan['requirements'],
                    libraryId=plan['libraryId'], libraryName=plan['libraryName'], questionCount=plan['questionCount'],
                    questionType=plan['questionType'], clientRequestId=ident)
        for index in range(len(plan['files'])):
            try:
                part_path(store, ident, index).unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning('Could not remove a completed upload fragment')
        return receipt
