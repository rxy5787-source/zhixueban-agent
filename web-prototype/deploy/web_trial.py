"""Separate, browser-scoped deployment entry point for the Web trial."""

from contextlib import asynccontextmanager
import hashlib
import hmac
import ipaddress
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .job_store import Store
from .account_space import resolve_account
from .account_web import account_authorization, account_routes, materials_db
from .model_status import generation_readiness
from .web_api import WebStore, init_web_tables, request_store_override, routes
from .worker import Runner
from .trial_body_limit import RequestBodyLimit
from . import resumable_uploads, study_chat, web_api
from .job_timing import timing_report
from .observability import event


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
    def __init__(self, root, maximum, *, local_preview=False, account_only=False):
        self.root = root
        self.maximum = maximum
        self.local_preview = local_preview
        self.lock = threading.Lock()
        if not account_only:
            root.mkdir(parents=True, exist_ok=True)
        self.stores = {}
        self.admissions = {}
        for path in (root.iterdir() if root.is_dir() and not root.is_symlink() else ()):
            if (path.is_dir() and not path.is_symlink() and SPACE_ID.fullmatch(path.name)
                    and (not account_only or ((path / 'jobs.sqlite3').is_file()
                         and not (path / 'jobs.sqlite3').is_symlink() and (path / 'materials.sqlite3').is_file()))):
                self.stores[path.name] = self.open(path.name)

    def open(self, ident):
        store = TrialStore(self.root / ident, local_preview=self.local_preview)
        init_web_tables(store)
        with store.db() as db:
            resumable_uploads.init_tables(db)
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

    def for_account(self, identity):
        jobs = identity.path / 'jobs.sqlite3'
        if jobs.resolve() != jobs or (jobs.exists() and not (identity.path / 'materials.sqlite3').is_file()):
            raise HTTPException(503, '账号学习空间暂不可用')
        with materials_db(identity):
            pass
        ident = identity.path.name
        with self.lock:
            if ident not in self.stores:
                self.stores[ident] = self.open(ident)
            return self.stores[ident]


class TrialQueue(Runner):
    def __init__(self, root, spaces, account_spaces=None):
        super().__init__(Store(root))
        self.spaces = spaces
        self.account_spaces = account_spaces

    def stores(self):
        return self.spaces.snapshot() + (self.account_spaces.snapshot() if self.account_spaces else ())

    def oldest_queue(self):
        oldest = None
        for space in self.stores():
            with space.db() as db:
                row = db.execute("SELECT created FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row is not None and (oldest is None or row['created'] < oldest[0]):
                oldest = (row['created'], space)
        return oldest[1] if oldest else None

    def loop(self):
        for space in self.stores():
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
                            event('worker_error', job_id=job['id'], error_code='worker_error')
                            space.update(job['id'], 'failed', '处理进程异常退出', error='出题服务处理失败，可稍后重试。')
                        continue
            except Exception:
                event('queue_error', error_code='database_error')
            self.stop.wait(0.5)


def create_app(data_root, frontend, origin, secret, maximum_spaces=32, *, start_worker=True,
               access_code=None, trust_cloudflare_headers=False, local_preview=False, landing_origin=None,
               account_login=False):
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
    if account_login and not (secure or local_preview):
        raise ValueError('Account login requires HTTPS except in loopback development')

    if access_code is not None and not 12 <= len(access_code) <= 128:
        raise ValueError('Use a trial access code with 12 to 128 characters')
    if landing_origin:
        landing = urlsplit(landing_origin)
        local_landing = local_preview and landing.scheme == 'http' and landing.hostname in {'127.0.0.1', 'localhost'}
        if (not landing.hostname or landing.username is not None or landing.path or landing.query or landing.fragment
                or not (landing.scheme == 'https' or local_landing)):
            raise ValueError('TRIAL_LANDING_ORIGIN must be an exact HTTPS origin')
        if secure and not access_code:
            raise ValueError('An online study landing page requires TRIAL_ACCESS_CODE')

    readiness_lock = threading.Lock()
    readiness_checked_at = float('-inf')
    model_available = None
    key = hmac.digest(secret.encode(), access_code.encode(), 'sha256') if access_code else secret.encode()
    probe = hmac.new(key, b'local-health-probe', hashlib.sha256).hexdigest()
    login_attempts = {}
    login_lock = threading.Lock()
    cookie_name = '__Host-zhixue-trial' if secure else 'zhixue-trial'
    spaces = TrialSpaces(data_root / 'spaces', maximum_spaces, local_preview=local_preview)
    account_spaces = TrialSpaces(data_root / 'account-spaces', maximum_spaces,
                                 local_preview=local_preview, account_only=True) if account_login else None
    worker = TrialQueue(data_root / 'queue', spaces, account_spaces)

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

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({'detail': '请检查输入格式和长度。'}, status_code=422,
                            headers={'Cache-Control': 'no-store'})

    @app.exception_handler(sqlite3.IntegrityError)
    async def database_constraint(request, error):
        if str(error) == 'trial_library_limit':
            return JSONResponse({'detail': '已达到当前试用空间的知识库数量上限。'}, status_code=429)
        event('constraint_error', request_id=getattr(request.state, 'request_id', None), error_code='database_error')
        return JSONResponse({'detail': '学习数据暂时无法保存，请稍后重试。'}, status_code=500)

    @app.middleware('http')
    async def browser_boundary(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        try:
            response = await guarded_request(request, call_next)
        except Exception:
            event('request_error', request_id=request_id, error_code='internal_error')
            response = JSONResponse({'detail': '服务暂时无法处理请求，请稍后重试。'}, status_code=500)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path in {'/account', '/learn'}:
            response.headers['Content-Security-Policy'] += "; script-src 'self'; object-src 'none'; connect-src 'self'"
        return response

    async def guarded_request(request, call_next):
        path = request.url.path
        expected = request.headers.get('x-zhixue-learner')
        account_study = path.startswith('/api/') and not path.startswith('/api/account/') and expected is not None
        if path in {'/account', '/learn'} or path.startswith('/api/account/') or account_study:
            headers = {'Cache-Control': 'no-store'}
            if not account_login or (not secure and (not request.client or request.client.host not in {'127.0.0.1', '::1'})):
                return JSONResponse({'detail': 'Not Found'}, status_code=404, headers=headers)
            supplied_origin = request.headers.get('origin')
            unsafe = request.method not in {'GET', 'HEAD', 'OPTIONS'}
            if (supplied_origin not in {None, origin} or
                    (unsafe and (supplied_origin != origin or request.headers.get('x-zhixue-account') != '1'))):
                return JSONResponse({'detail': '请从知学伴同源页面提交请求。'}, status_code=403, headers=headers)
            if account_study:
                try:
                    identity = await run_in_threadpool(resolve_account, account_authorization(request, secure), data_root)
                    if identity.username != expected:
                        raise HTTPException(401, '账号已切换，请重新进入学习空间。')
                    store = await run_in_threadpool(account_spaces.for_account, identity)
                except HTTPException as error:
                    return JSONResponse({'detail': error.detail}, status_code=error.status_code, headers=headers)
                override = request_store_override.set(store)
                try:
                    response = await call_next(request)
                finally:
                    request_store_override.reset(override)
            else:
                response = await call_next(request)
            response.headers.update(headers)
            return response

        if access_code and (request.url.path == '/api/health' or (
                request.url.path == '/healthz' and not hmac.compare_digest(request.headers.get('x-trial-probe', '').encode(), probe.encode()))):
            return JSONResponse({'detail': 'Not Found'}, status_code=404)
        needs_origin = request.url.path.startswith('/api/') or request.url.path == '/trial-access'
        if not needs_origin:
            return await call_next(request)
        supplied_origin = request.headers.get('origin')
        if (supplied_origin and supplied_origin != origin) or (
                request.method not in {'GET', 'HEAD', 'OPTIONS'} and supplied_origin != origin):
            return JSONResponse({'detail': '请从试用页面提交请求。'}, status_code=403)
        if request.url.path == '/trial-access':
            return await call_next(request)
        ident = existing_space(request)
        if ident is None:
            return JSONResponse({'detail': '请打开试用首页并输入访问码。' if access_code else '请刷新试用首页以建立浏览器会话。'}, status_code=401)
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

    @app.get('/study-availability')
    def study_availability(request: Request):
        nonlocal readiness_checked_at, model_available
        if not landing_origin or request.headers.get('origin') != landing_origin:
            raise HTTPException(404)
        headers = {'Access-Control-Allow-Origin': landing_origin, 'Vary': 'Origin', 'Cache-Control': 'no-store'}
        if readiness_lock.acquire(blocking=False):
            try:
                if time.monotonic() - readiness_checked_at >= 5:
                    model_available = generation_readiness(timeout=(1, 3))['generationReady']
                    readiness_checked_at = time.monotonic()
            finally:
                readiness_lock.release()
        else:
            return JSONResponse({'status': 'checking'}, headers=headers)
        return JSONResponse({'status': 'ready' if model_available else 'model-unavailable'}, headers=headers)

    @app.get('/')
    def index(request: Request):
        ident = existing_space(request)
        if ident is None:
            if access_code:
                return login_page()
            ident = spaces.new(visitor_address(request))
        response = FileResponse(frontend / 'index.html', headers={'Cache-Control': 'no-store'})
        return attach_cookie(response, ident)

    if account_login:
        @app.get('/account')
        @app.get('/learn')
        def account_page():
            return FileResponse(frontend / 'index.html')

        app.include_router(account_routes(data_root.resolve(), secure=secure))

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
        destination = '/#home/study' if landing_origin else '/'
        return attach_cookie(RedirectResponse(destination, status_code=303, headers={'Cache-Control': 'no-store'}), ident)

    @app.get('/favicon.svg')
    def favicon():
        return FileResponse(frontend / 'favicon.svg')

    @app.get('/api/evaluation-preflight')
    def evaluation_preflight(request: Request):
        if not local_preview or request.client is None or request.client.host not in {'127.0.0.1', '::1'}:
            raise HTTPException(404)
        if existing_space(request) is None:
            raise HTTPException(401, '本地评测会话无效')
        return {'localPreview': True, **generation_readiness()}

    @app.get('/api/generation-tasks/{ident}/timing')
    def task_timing(ident: str):
        # Middleware selects a verified Store; task() checks resource ownership.
        job, _ = web_api.task(ident)
        with web_api.request_store().db() as db:
            events = [dict(row) for row in db.execute(
                'SELECT state,stage,created FROM job_events WHERE job_id=? ORDER BY id', (ident,))]
            metric = db.execute('SELECT callback_elapsed_ms FROM job_archive_metrics WHERE job_id=?', (ident,)).fetchone()
        return timing_report(job, events, metric[0] if metric else None)

    app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')
    app.include_router(routes)
    app.include_router(resumable_uploads.router)
    app.include_router(study_chat.router)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[url.hostname])
    return app


def from_environment():
    return create_app(Path(os.environ['TRIAL_DATA_DIR']).resolve(),
                      Path(os.environ['TRIAL_FRONTEND_DIR']).resolve(),
                      os.environ['TRIAL_PUBLIC_ORIGIN'], os.environ['TRIAL_SECRET'],
                      int(os.environ.get('TRIAL_MAX_SPACES', '32')),
                      access_code=os.environ.get('TRIAL_ACCESS_CODE'),
                      trust_cloudflare_headers=os.environ.get('TRIAL_CLOUDFLARE_PROXY') == '1',
                      local_preview=os.environ.get('TRIAL_LOCAL_PREVIEW') == '1',
                      landing_origin=os.environ.get('TRIAL_LANDING_ORIGIN'),
                      account_login=os.environ.get('TRIAL_ACCOUNT_LOGIN') == '1')
