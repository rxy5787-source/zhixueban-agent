"""Read-only Agent API for one explicitly authorized Web learning space."""
from contextlib import closing
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .web_practice import weak_knowledge


LOGGER = logging.getLogger(__name__)
BEARER = HTTPBearer(auto_error=False)
SPACE_ID = re.compile(r'[0-9a-f]{48}')


class WeakPoint(BaseModel):
    knowledge_id: str
    name: str
    mastery: float = Field(ge=0, le=1)


class WeakKnowledgeResponse(BaseModel):
    user_id: str
    weak_knowledge: list[WeakPoint]


def from_environment() -> FastAPI:
    token = os.getenv('ZHIXUE_AGENT_TOKEN', '')
    space_id = os.getenv('ZHIXUE_AGENT_SPACE_ID', '')
    root = os.getenv('ZHIXUE_AGENT_TRIAL_DATA', '')
    user_id = os.getenv('ZHIXUE_AGENT_USER_ID', 'local-learner')
    if len(token) < 32 or any(ch.isspace() or not ch.isascii() for ch in token):
        raise RuntimeError('ZHIXUE_AGENT_TOKEN must contain at least 32 printable non-space ASCII characters')
    if not SPACE_ID.fullmatch(space_id) or not root:
        raise RuntimeError('Set ZHIXUE_AGENT_TRIAL_DATA and an authorized ZHIXUE_AGENT_SPACE_ID')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', user_id):
        raise RuntimeError('ZHIXUE_AGENT_USER_ID must be a non-sensitive alias of 1–64 characters')

    database = Path(root).resolve() / 'spaces' / space_id / 'jobs.sqlite3'
    if database.resolve() != database or not database.is_file():
        raise RuntimeError('The authorized Web space database does not exist at the configured location')
    digest = hashlib.sha256(token.encode('ascii')).digest()
    app = FastAPI(title='知学伴 Agent 学习查询')

    def authenticate(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER)]):
        presented = credentials.credentials if credentials else ''
        if not presented or not hmac.compare_digest(hashlib.sha256(presented.encode()).digest(), digest):
            raise HTTPException(401, '需要有效的 Agent 访问凭证', headers={'WWW-Authenticate': 'Bearer'})

    @app.get('/api/agent/weak-knowledge', response_model=WeakKnowledgeResponse,
             dependencies=[Depends(authenticate)])
    def list_weak_knowledge(
        response: Response,
        limit: Annotated[int, Query(ge=1, le=20)] = 3,
        requested_user: Annotated[str | None, Query(alias='user_id', max_length=64)] = None,
        requested_space: Annotated[str | None, Query(alias='space_id', max_length=48, include_in_schema=False)] = None,
    ):
        if requested_user not in (None, user_id) or requested_space not in (None, space_id):
            raise HTTPException(403, '凭证未获授权访问所请求的学习空间')
        response.headers['Cache-Control'] = 'no-store'
        started = perf_counter()
        try:
            if database.resolve() != database:
                raise sqlite3.OperationalError('Configured database path changed')
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
                db.row_factory = sqlite3.Row
                points = [
                    WeakPoint(knowledge_id=hashlib.sha256(json.dumps(
                        [row['library_id'], row['point_key']], ensure_ascii=False,
                    ).encode()).hexdigest(), name=row['label'], mastery=row['mastery'])
                    for row in weak_knowledge(db, limit)
                ]
        except (sqlite3.Error, OSError):
            LOGGER.warning('Agent weak-knowledge data unavailable')
            raise HTTPException(503, '学习数据暂不可读取') from None
        LOGGER.info('Agent weak-knowledge returned %d points in %.1f ms', len(points), (perf_counter() - started) * 1000)
        return WeakKnowledgeResponse(user_id=user_id, weak_knowledge=points)

    return app
