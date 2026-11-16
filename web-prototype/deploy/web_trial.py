"""Separate, browser-scoped deployment entry point for the Web trial."""

from contextlib import asynccontextmanager
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .job_store import Store
from .job_timing import timing_report
from .web_error_contract import error_code, safe_error_response
from .web_api import WebStore, init_web_tables, request_store_override, routes
from .worker import Runner
from .trial_body_limit import RequestBodyLimit
from . import resumable_uploads
from .study_practice_executor import ConfirmedPractice, dispatch_confirmed_practice, ensure_execution_tables, study_proposal
from .model_status import generation_readiness
from .agent_evaluation import evaluate_library
from .agent_recovery_policy import advise_recovery
from .web_content import OWNER


LOGGER = logging.getLogger(__name__)
SPACE_ID = re.compile(r'[0-9a-f]{48}')
UPLOAD_LIMIT = 25 * 1024 * 1024
COOKIE_LIFETIME = 30 * 24 * 60 * 60
MAX_JOBS_PER_SPACE = 8
MAX_LIBRARIES_PER_SPACE = 50

class TrialStore(WebStore):
    def __init__(self, root, *, local_preview=False):
        super().__init__(root)
        self.local_preview = local_preview

    def check_submission(self, db):
        if db.execute("SELECT 1 FROM jobs WHERE state IN ('queued', 'running') LIMIT 1").fetchone():
            raise HTTPException(409, '当前已有出题任务，请完成或取消后再提交。')
        if not self.local_preview and db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= MAX_JOBS_PER_SPACE:
            raise HTTPException(429, '当前试用空间已用完出题次数。')


class TrialSpaces:
    def __init__(self, root, maximum, *, local_preview=False):
        self.root = root
        self.maximum = maximum
        self.local_preview = local_preview
        self.lock = threading.Lock()
        root.mkdir(parents=True, exist_ok=True)
        self.stores = {}
        self.admissions = {}
        for path in root.iterdir():
            if path.is_dir() and not path.is_symlink() and SPACE_ID.fullmatch(path.name):
                self.stores[path.name] = self.open(path.name)

    def open(self, ident):
        store = TrialStore(self.root / ident, local_preview=self.local_preview)
        init_web_tables(store)
        with store.db() as db:
            resumable_uploads.init_tables(db)
            ensure_execution_tables(db)
            db.executescript(f'''
                CREATE TRIGGER IF NOT EXISTS limit_trial_libraries
                BEFORE INSERT ON web_libraries
                WHEN NOT EXISTS (SELECT 1 FROM web_libraries WHERE id = NEW.id)
                AND (SELECT COUNT(*) FROM web_libraries) >= {MAX_LIBRARIES_PER_SPACE}
                BEGIN SELECT RAISE(ABORT, 'trial_library_limit'); END;
            ''')
        return store

    def new(self, address):
        with self.lock:
            if len(self.stores) >= self.maximum:
                raise HTTPException(503, '试用名额已满，请联系分享者。')
            hour = int(time.time()) // 3600
            self.admissions = {ip: entry for ip, entry in self.admissions.items() if entry[0] == hour}
            count = self.admissions.get(address, (hour, 0))[1]
            if count >= 6:
                raise HTTPException(429, '当前网络创建了过多试用空间，请稍后重试。')
            ident = secrets.token_hex(24)
            self.stores[ident] = self.open(ident)
            self.admissions[address] = (hour, count + 1)
            return ident

    def get(self, ident):
        with self.lock:
            return self.stores.get(ident)

    def snapshot(self):
        with self.lock:
            return tuple(self.stores.values())


class TrialQueue(Runner):
    def __init__(self, root, spaces):
        super().__init__(Store(root))
        self.spaces = spaces

    def oldest_queue(self):
        oldest = None
        for space in self.spaces.snapshot():
            with space.db() as db:
                row = db.execute("SELECT created FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row is not None and (oldest is None or row['created'] < oldest[0]):
                oldest = (row['created'], space)
        return oldest[1] if oldest else None

    def loop(self):
        for space in self.spaces.snapshot():
            space.recover()
        while not self.stop.is_set():
            try:
                space = self.oldest_queue()
                if space is not None:
                    job = space.claim()
                    if job is not None:
                        runner = Runner(space)
                        runner.stop = self.stop
                        try:
                            runner.supervise(job)
                        except Exception:
                            LOGGER.exception('Trial job failed')
                            space.update(job['id'], 'failed', '处理进程异常退出', error='出题服务处理失败，可稍后重试。')
                        continue
            except Exception:
                LOGGER.exception('Trial queue could not be read')
            self.stop.wait(0.5)


def create_app(data_root, frontend, origin, secret, maximum_spaces=32, *, start_worker=True,
               access_code=None, trust_cloudflare_headers=False, local_preview=False):
    url = urlsplit(origin)
    secure = url.scheme == 'https'
    if (not url.hostname or url.username is not None or url.path or url.query or url.fragment
            or (not secure and not (url.scheme == 'http' and url.hostname in {'127.0.0.1', 'localhost'}))):
        raise ValueError('TRIAL_PUBLIC_ORIGIN must be an HTTPS origin, or loopback HTTP for testing')
    if len(secret) < 32 or not 1 <= maximum_spaces <= 128:
        raise ValueError('Use a random TRIAL_SECRET and a trial space limit between 1 and 128')
    if local_preview and (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost'}
                          or access_code or trust_cloudflare_headers):
        raise ValueError('Unlimited task history is only available in local preview')

    if access_code is not None and not 12 <= len(access_code) <= 128:
        raise ValueError('Use a trial access code with 12 to 128 characters')
    key = hmac.digest(secret.encode(), access_code.encode(), 'sha256') if access_code else secret.encode()
    probe = hmac.new(key, b'local-health-probe', hashlib.sha256).hexdigest()
    login_attempts = {}
    login_lock = threading.Lock()
    cookie_name = '__Host-zhixue-trial' if secure else 'zhixue-trial'
    spaces = TrialSpaces(data_root / 'spaces', maximum_spaces, local_preview=local_preview)
    worker = TrialQueue(data_root / 'queue', spaces)

    def signed_cookie(ident, expiry):
        value = f'{ident}.{expiry}'
        signature = hmac.new(key, value.encode(), hashlib.sha256).hexdigest()
        return f'{value}.{signature}'

    def existing_space(request):
        value = request.cookies.get(cookie_name, '')
        fields = value.split('.')
        if len(fields) != 3 or not SPACE_ID.fullmatch(fields[0]) or not re.fullmatch(r'[0-9]{1,12}', fields[1]):
            return None
        ident, expiry, signature = fields
        if not re.fullmatch(r'[0-9a-f]{64}', signature) or int(expiry) <= int(time.time()):
            return None
        if not hmac.compare_digest(value, signed_cookie(ident, expiry)) or spaces.get(ident) is None:
            return None
        return ident

    def visitor_address(request):
        address = request.client.host if request.client else 'unknown'
        if trust_cloudflare_headers and address in {'127.0.0.1', '::1'}:
            forwarded = request.headers.get('cf-connecting-ip', '')
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
        return address

    def attach_cookie(response, ident):
        response.set_cookie(cookie_name, signed_cookie(ident, int(time.time()) + COOKIE_LIFETIME),
                            max_age=COOKIE_LIFETIME, httponly=True, secure=secure, samesite='lax', path='/')
        return response

    def login_page(error='', status=200):
        template = Path(__file__).with_name('trial_access.html').read_text(encoding='utf-8')
        message = f'<p class="error" role="alert">{error}</p>' if error else ''
        return HTMLResponse(template.replace('<!--ACCESS_ERROR-->', message), status_code=status,
                            headers={'Cache-Control': 'no-store'})

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            if start_worker:
                await run_in_threadpool(worker.close)

    app = FastAPI(title='知学伴在线试用', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(RequestBodyLimit, limit=UPLOAD_LIMIT)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException):
        # Public details remain user-friendly; identifiers and input data never
        # enter the machine-readable code or request ID.
        detail = error.detail if isinstance(error.detail, str) else "请求无法处理。"
        return safe_error_response(request, error.status_code, detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # FastAPI's default error items can include raw "input", user text,
        # filenames or secret form values. Never serialize error.errors().
        return safe_error_response(request, 422, "请求参数格式无效，请检查后重试。")


    @app.exception_handler(sqlite3.IntegrityError)
    async def database_constraint(request, error):
        if str(error) == 'trial_library_limit':
            return safe_error_response(request, 429, '已达到当前试用空间的知识库数量上限。')
        if str(error) == 'task_retry_depth_limit':
            return safe_error_response(request, 409, '每份任务最多允许一次人工重试，请检查失败原因。')
        # Avoid exception stacks/SQL values in logs; only a server-issued
        # identifier is safe to carry into operational diagnostics.
        LOGGER.error('Trial constraint failure request_id=%s',
                     getattr(request.state, 'request_id', 'unavailable'))
        return safe_error_response(request, 500, '学习数据暂时无法保存，请稍后重试。')

    @app.middleware('http')
    async def browser_boundary(request: Request, call_next):
        request.state.request_id = secrets.token_hex(12)
        try:
            response = await guarded_request(request, call_next)
        except Exception as error:
            # Unexpected application failures are mapped at the request
            # boundary, not serialized with traceback, SQL, files or prompts.
            # Log only a correlation ID and exception *type*, never its value.
            LOGGER.error('Trial unhandled request request_id=%s failure_type=%s',
                         request.state.request_id, type(error).__name__)
            response = safe_error_response(
                request, 500, '服务暂时无法处理请求，请稍后重试。')
        response.headers['X-Request-ID'] = request.state.request_id
        if response.status_code >= 400:
            response.headers['X-Error-Code'] = error_code(response.status_code)
            if request.url.path.startswith('/api/'):
                response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    async def guarded_request(request, call_next):
        if access_code and (request.url.path == '/api/health' or (
                request.url.path == '/healthz' and not hmac.compare_digest(request.headers.get('x-trial-probe', '').encode(), probe.encode()))):
            return safe_error_response(request, 404, 'Not Found')
        needs_origin = request.url.path.startswith('/api/') or request.url.path == '/trial-access'
        if not needs_origin:
            return await call_next(request)
        supplied_origin = request.headers.get('origin')
        if (supplied_origin and supplied_origin != origin) or (
                request.method not in {'GET', 'HEAD', 'OPTIONS'} and supplied_origin != origin):
            return safe_error_response(request, 403, '请从试用页面提交请求。')
        if request.url.path == '/trial-access':
            return await call_next(request)
        ident = existing_space(request)
        if ident is None:
            return safe_error_response(request, 401, '请打开试用首页并输入访问码。' if access_code else '请刷新试用首页以建立浏览器会话。')
        override = request_store_override.set(spaces.get(ident))
        try:
            response = await call_next(request)
        finally:
            request_store_override.reset(override)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/healthz')
    def health():
        return {'ok': True}

    @app.get('/')
    def index(request: Request):
        ident = existing_space(request)
        if ident is None:
            if access_code:
                return login_page()
            ident = spaces.new(visitor_address(request))
        response = FileResponse(frontend / 'index.html', headers={'Cache-Control': 'no-store'})
        return attach_cookie(response, ident)

    @app.post('/trial-access')
    async def enter_trial(request: Request):
        if access_code is None:
            raise HTTPException(404)
        address = visitor_address(request)
        now = time.monotonic()
        with login_lock:
            expired = [ip for ip, (_, expiry) in login_attempts.items() if expiry <= now]
            for ip in expired:
                del login_attempts[ip]
            attempts, expiry = login_attempts.get(address, (0, now + 600))
            if attempts >= 5 or (address not in login_attempts and len(login_attempts) >= 2048):
                return login_page('访问码尝试次数过多，请十分钟后重试。', 429)
            login_attempts[address] = (attempts + 1, expiry)
        form = await request.form()
        supplied = form.get('accessCode', '')
        if not isinstance(supplied, str) or len(supplied) > 128 or not hmac.compare_digest(
                hashlib.sha256(supplied.encode()).digest(), hashlib.sha256(access_code.encode()).digest()):
            return login_page('访问码不正确，请向分享者核对。', 401)
        with login_lock:
            login_attempts.pop(address, None)
        ident = existing_space(request) or spaces.new(address)
        return attach_cookie(RedirectResponse('/', status_code=303, headers={'Cache-Control': 'no-store'}), ident)

    @app.get('/api/evaluation-preflight')
    def evaluation_preflight(request: Request):
        # Exposes evaluation permission ONLY for loopback-local preview.
        # A public trial cannot opt in to unlimited experiments.
        if not local_preview or request.client is None or (
                request.client.host not in {'127.0.0.1', '::1', 'testclient'}):
            raise HTTPException(404)
        if existing_space(request) is None:
            raise HTTPException(401, '本地评测会话无效')
        return {'localPreview': True, **generation_readiness()}

    @app.get('/api/study-plans/{library_id}')
    def study_plan(library_id: str, request: Request):
        # The verified session picks the store; the path only picks a library
        # inside that store. No user-selected directory or owner identifier.
        space_id = existing_space(request)
        if space_id is None:
            raise HTTPException(401, '请先建立浏览器会话')
        current_store = spaces.get(space_id)
        if current_store is None:
            raise HTTPException(401, '浏览器会话已失效')
        with current_store.db() as db:
            return study_proposal(db, library_id)

    @app.post('/api/study-plans/{library_id}/execute', status_code=202)
    def execute_study_plan(library_id: str, payload: ConfirmedPractice, request: Request):
        # A POST from the verified study space is an explicit execution request.
        ident = existing_space(request)
        if ident is None or spaces.get(ident) is None:
            raise HTTPException(401, '请先建立浏览器会话')
        return dispatch_confirmed_practice(
            spaces.get(ident), library_id, payload, generation_readiness,
        )

    @app.get('/api/generation-tasks/{task_id}/recovery-advice')
    def recovery_advice(task_id: str, request: Request):
        # Never allow a task ID to cross the signed visitor's data boundary.
        ident = existing_space(request)
        current = spaces.get(ident) if ident is not None else None
        if current is None:
            raise HTTPException(401, '请先建立浏览器会话')
        with current.db() as db:
            row = db.execute(
                """SELECT j.id, j.state, j.result, j.request, t.library_id
                   FROM jobs AS j JOIN web_tasks AS t ON t.task_id=j.id
                   WHERE j.id=? AND j.owner=?""",
                (task_id, OWNER),
            ).fetchone()
            if row is None:
                raise HTTPException(404, '生成任务不存在')

            depth, cursor, seen = 0, task_id, {task_id}
            for _ in range(16):
                parent = db.execute(
                    """SELECT r.original_id FROM web_task_retries AS r
                       JOIN jobs AS j ON j.id=r.original_id AND j.owner=?
                       JOIN web_tasks AS t ON t.task_id=j.id
                       WHERE r.retry_id=?""",
                    (OWNER, cursor),
                ).fetchone()
                if parent is None:
                    break
                cursor = parent['original_id']
                if cursor in seen:
                    raise HTTPException(409, '任务重试链异常，暂停恢复建议')
                depth += 1
                seen.add(cursor)
            else:
                raise HTTPException(409, '重试链过长，暂停恢复建议')

            existing = db.execute(
                """SELECT j.id FROM web_task_retries r
                   JOIN jobs j ON j.id=r.retry_id AND j.owner=?
                   JOIN web_tasks t ON t.task_id=j.id
                   WHERE r.original_id=?""",
                (OWNER, task_id),
            ).fetchone()
            request_body = json.loads(row['request'])
            source_ids = request_body.get('fileIds', [])
            sources_ok = isinstance(source_ids, list) and bool(source_ids)
            if sources_ok:
                for file_id in source_ids:
                    source = db.execute(
                        'SELECT path FROM files WHERE id=? AND owner=?',
                        (file_id, OWNER),
                    ).fetchone()
                    removed = db.execute(
                        """SELECT 1 FROM web_removed_items
                           WHERE library_id=? AND kind='source' AND item_id=?""",
                        (row['library_id'], file_id),
                    ).fetchone()
                    if source is None or removed or not Path(source['path']).is_file():
                        sources_ok = False
                        break
            return advise_recovery(
                {'id': row['id'], 'state': row['state'],
                 'result': json.loads(row['result'])},
                existing_retry_id=existing['id'] if existing else None,
                retry_depth=depth,
                source_available=sources_ok,
            )

    @app.get('/api/generation-tasks/{task_id}/timing')
    def task_stage_timing(task_id: str, request: Request):
        """Read-only allowlisted timing report for the signed browser space."""
        ident = existing_space(request)
        current = spaces.get(ident) if ident is not None else None
        if current is None:
            raise HTTPException(401, '请先建立浏览器会话')
        with current.db() as db:
            job = db.execute(
                """SELECT j.id,j.state,j.created,j.updated FROM jobs j
                   JOIN web_tasks t ON t.task_id=j.id
                   WHERE j.id=? AND j.owner=?""",
                (task_id, OWNER),
            ).fetchone()
            if job is None:
                raise HTTPException(404, '生成任务不存在')
            events = [dict(row) for row in db.execute(
                'SELECT state,stage,created FROM job_events WHERE job_id=? ORDER BY id',
                (task_id,),
            )]
            metric = db.execute(
                'SELECT callback_elapsed_ms FROM job_archive_metrics WHERE job_id=?',
                (task_id,),
            ).fetchone()
        return timing_report(
            dict(job), events,
            metric['callback_elapsed_ms'] if metric else None,
        )

    @app.get('/api/study-evaluation/{library_id}')
    def study_evaluation(library_id: str, request: Request):
        # Read only metadata from the current signed browser session.
        ident = existing_space(request)
        if ident is None or spaces.get(ident) is None:
            raise HTTPException(401, '请先建立浏览器会话')
        with spaces.get(ident).db() as db:
            return evaluate_library(db, library_id)

    @app.get('/favicon.svg')
    def favicon():
        return FileResponse(frontend / 'favicon.svg')

    app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')
    app.include_router(routes)
    app.include_router(resumable_uploads.router)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[url.hostname])
    return app


def from_environment():
    return create_app(Path(os.environ['TRIAL_DATA_DIR']).resolve(),
                      Path(os.environ['TRIAL_FRONTEND_DIR']).resolve(),
                      os.environ['TRIAL_PUBLIC_ORIGIN'], os.environ['TRIAL_SECRET'],
                      int(os.environ.get('TRIAL_MAX_SPACES', '32')),
                      access_code=os.environ.get('TRIAL_ACCESS_CODE'),
                      trust_cloudflare_headers=os.environ.get('TRIAL_CLOUDFLARE_PROXY') == '1',
                      local_preview=os.environ.get('TRIAL_LOCAL_PREVIEW') == '1')
