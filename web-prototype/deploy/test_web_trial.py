import concurrent.futures
from pathlib import Path
import time

from fastapi.testclient import TestClient
from requests import ReadTimeout

from backend import web_api
from backend.web_trial import COOKIE_LIFETIME, MAX_JOBS_PER_SPACE, MAX_LIBRARIES_PER_SPACE, create_app
from backend.web_trial import TrialStore
from backend.worker import Runner


ORIGIN = 'https://trial.example.test'
SECRET = 'testing-secret-only-' * 2
COOKIE = '__Host-zhixue-trial'


def app_at(tmp_path, maximum=32, *, start_worker=False, **options):
    frontend = tmp_path / 'public'
    (frontend / 'assets').mkdir(parents=True, exist_ok=True)
    (frontend / 'index.html').write_text('<title>Trial</title>')
    return create_app(tmp_path / 'data', frontend, ORIGIN, SECRET, maximum, start_worker=start_worker, **options)


def client(app):
    return TestClient(app, base_url=ORIGIN)


def create_exam(browser, library):
    return browser.post('/api/exam-practice-tasks', headers={'Origin': ORIGIN}, json={
        'libraryId': library, 'libraryName': library, 'questionCount': 1, 'topic': 'complement',
    })



def test_stage_timing_is_session_scoped_and_strips_private_text(tmp_path):
    from backend.job_timing import phase_from_stage
    app = app_at(tmp_path)
    first, second = client(app), client(app)
    first.get('/')
    second.get('/')
    task = create_exam(first, 'sql').json()['taskId']
    url = f'/api/generation-tasks/{task}/timing'
    assert second.get(url).status_code == 404
    assert client(app).get(url).status_code == 401
    assert first.get('/api/generation-tasks/missing/timing').status_code == 404

    store = browser_store(tmp_path, first)
    secret = 'token-PLEASE-NEVER-LOG'
    store.update(task, 'running', '解析 ' + secret + '.docx')
    store.update(task, 'running', '正在识别扫描文字 · ' + secret)
    store.update(task, 'running', 'AI生成题目 · ' + secret)
    store.update(task, 'running', '自动质量初筛 · ' + secret)
    store.update(task, 'failed', '处理失败 · ' + secret, error='账号凭据 '+secret)

    response = first.get(url)
    assert response.status_code == 200, response.text
    info = response.json()
    assert info['taskId'] == task
    assert info['state'] == 'failed'
    assert info['errorCategory'] == 'task_failed'
    assert info['queueWaitMs'] is None  # Synthetic task has no claim event.
    assert info['archiveCallbackMs'] is None
    assert info['terminalWallTimeMs'] is not None
    assert set(info['phaseElapsedMs']).issubset(
        {'preparation', 'parsing', 'ocr', 'knowledge', 'generation', 'quality', 'checkpoint', 'other'})
    assert 'parsing' in info['phaseElapsedMs']
    assert 'ocr' in info['phaseElapsedMs']
    assert 'generation' in info['phaseElapsedMs']
    assert 'quality' in info['phaseElapsedMs']
    assert secret not in response.text
    assert '.docx' not in response.text
    assert '凭据' not in response.text
    assert phase_from_stage('未知内容:' + secret) == 'other'
    assert first.get(url, headers={'Origin': 'https://evil.example'}).status_code == 403


def test_stage_timing_claim_and_archive_callback_are_measured(tmp_path):
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    task = create_exam(browser, 'sql').json()['taskId']
    store = browser_store(tmp_path, browser)
    claimed = store.claim()
    assert claimed['id'] == task
    store.update(task, 'running', 'AI生成题目')
    store.update(task, 'running', '自动质量初筛')
    store.update(task, 'succeeded', '已结束', {'content': {'libraries': []}})
    with store.db() as db:
        assert db.execute(
            'SELECT COUNT(*) FROM job_events WHERE job_id=? AND stage=?',
            (task, '准备解析'),
        ).fetchone()[0] == 1
        assert db.execute(
            'SELECT COUNT(*) FROM job_archive_metrics WHERE job_id=?',
            (task,),
        ).fetchone()[0] == 1
    data = browser.get(f'/api/generation-tasks/{task}/timing').json()
    assert data['queueWaitMs'] is not None
    assert data['archiveCallbackMs'] is not None
    assert data['archiveCallbackMs'] >= 0
    assert data['timingBasis'] == 'completed_checkpoint_intervals'
    assert data['terminalWallTimeMs'] is not None
    assert data['errorCategory'] is None
    assert 'generation' in data['phaseElapsedMs']
    assert 'quality' in data['phaseElapsedMs']
    # Re-reading metrics cannot mutate the checkpoint event history.
    with store.db() as db:
        before = db.execute('SELECT COUNT(*) FROM job_events WHERE job_id=?', (task,)).fetchone()[0]
    browser.get(f'/api/generation-tasks/{task}/timing')
    with store.db() as db:
        after = db.execute('SELECT COUNT(*) FROM job_events WHERE job_id=?', (task,)).fetchone()[0]
    assert before == after


def test_stage_timing_direct_algorithm_handles_empty_and_clock_regression():
    from backend.job_timing import timing_report
    job = {'id': 'f'*32, 'created': 100.0, 'updated': 112.0, 'state': 'interrupted'}
    empty = timing_report(job, [])
    assert empty['phaseElapsedMs'] == {}
    assert empty['queueWaitMs'] is None
    assert empty['errorCategory'] == 'task_interrupted'
    events = [
        {'state': 'running', 'stage': '准备解析', 'created': 106.0},
        {'state': 'running', 'stage': 'AI生成题目 token-SENSITIVE', 'created': 104.0},
        {'state': 'interrupted', 'stage': '中断 token-SENSITIVE', 'created': 112.0},
    ]
    result = timing_report(job, events)
    assert result['queueWaitMs'] == 6000
    assert result['phaseElapsedMs']['preparation'] == 0
    assert result['phaseElapsedMs']['generation'] == 6000
    assert 'SENSITIVE' not in str(result)


def test_sessions_are_isolated_and_survive_restart(tmp_path):
    app = app_at(tmp_path)
    first, second = client(app), client(app)
    assert first.get('/api/libraries').status_code == 401
    index = first.get('/')
    assert index.status_code == 200
    for flag in ('Secure', 'HttpOnly', 'SameSite=lax', 'Path=/', f'Max-Age={COOKIE_LIFETIME}'):
        assert flag in index.headers['Set-Cookie']
    assert index.headers['Cache-Control'] == 'no-store'
    assert second.get('/').status_code == 200
    assert first.cookies[COOKIE] != second.cookies[COOKIE]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(create_exam, first, 'first-library'), pool.submit(create_exam, second, 'second-library')]
        first_job, second_job = [request.result() for request in requests]
    assert first_job.status_code == second_job.status_code == 201
    ident = first_job.json()['taskId']
    first_task = f'/api/generation-tasks/{ident}'
    assert first.get(first_task).status_code == 200
    assert second.get(first_task).status_code == 404
    assert first.get(f"/api/generation-tasks/{second_job.json()['taskId']}").status_code == 404
    assert first.get('/api/libraries').headers['Cache-Control'] == 'no-store'
    assert 'first-library' in first.get('/api/libraries').text
    assert 'first-library' not in second.get('/api/libraries').text

    restored = client(app_at(tmp_path))
    restored.cookies.set(COOKIE, first.cookies[COOKIE])
    assert restored.get(first_task).status_code == 200


def test_boundaries_and_limits(tmp_path):
    app = app_at(tmp_path, maximum=1)
    browser = client(app)
    assert browser.get('/healthz').status_code == 200
    assert browser.get('/').status_code == 200
    assert client(app).get('/').status_code == 503
    assert browser.get('/', headers={'Host': 'untrusted.test'}).status_code == 400
    path = '/api/libraries/test'
    assert browser.put(path, json={'title': 'not accepted'}).status_code == 403
    assert browser.put(path, headers={'Origin': 'https://untrusted.test'}, json={'title': 'not accepted'}).status_code == 403
    headers = {'Origin': ORIGIN}
    assert browser.put(path, headers={**headers, 'Content-Length': '30000000'}, json={'title': 'blocked'}).status_code == 413

    for index in range(MAX_LIBRARIES_PER_SPACE):
        response = browser.put(f'/api/libraries/test-{index}', headers=headers, json={'title': '课程'})
        assert response.status_code == 200, response.text
    assert browser.put(path, headers=headers, json={'title': 'overflow'}).status_code == 429
    assert browser.put('/api/libraries/test-0', headers=headers, json={'title': '课程改名'}).status_code == 200

    jobs = [create_exam(browser, 'test-0') for _ in range(MAX_JOBS_PER_SPACE)]
    assert all(job.status_code == 201 for job in jobs)
    assert create_exam(browser, 'test-0').status_code == 429
    ident = jobs[0].json()['taskId']
    assert browser.post(f'/api/generation-tasks/{ident}/retry', headers=headers).status_code == 429

    visitor = client(app)
    visitor.cookies.set(COOKIE, browser.cookies[COOKIE][:-1] + ('a' if browser.cookies[COOKIE][-1] != 'a' else 'b'))
    assert visitor.get('/api/libraries').status_code == 401


def test_existing_local_space_can_create_more_than_eight_tasks(tmp_path):
    origin = 'http://127.0.0.1:8095'
    frontend = tmp_path / 'public'
    (frontend / 'assets').mkdir(parents=True)
    (frontend / 'index.html').write_text('<title>Preview</title>')
    data = tmp_path / 'data'
    original = create_app(data, frontend, origin, SECRET, start_worker=False)
    with TestClient(original, base_url=origin, headers={'Origin': origin}) as browser:
        assert browser.get('/').status_code == 200
        payload = {'libraryId': 'existing', 'libraryName': 'Existing', 'questionCount': 1, 'topic': 'complement'}
        tasks = [browser.post('/api/exam-practice-tasks', json=payload) for _ in range(MAX_JOBS_PER_SPACE)]
        assert all(task.status_code == 201 for task in tasks)
        assert browser.post('/api/exam-practice-tasks', json=payload).status_code == 429
        cookie = browser.cookies['zhixue-trial']
        first_id = tasks[0].json()['taskId']

    updated = create_app(data, frontend, origin, SECRET, start_worker=False, local_preview=True)
    with TestClient(updated, base_url=origin, headers={'Origin': origin}, cookies={'zhixue-trial': cookie}) as browser:
        assert browser.get(f'/api/generation-tasks/{first_id}').status_code == 200
        assert browser.post('/api/exam-practice-tasks', json=payload).status_code == 201


def test_invitation_gate_rate_limit_and_private_routes(tmp_path):
    code = 'trial-secret-123456'
    app = app_at(tmp_path, access_code=code)
    visitor = client(app)
    assert '试用访问码' in visitor.get('/').text
    assert not visitor.cookies
    assert visitor.get('/api/libraries').status_code == 401
    assert visitor.get('/healthz').status_code == 404
    assert visitor.get('/api/health').status_code == 404
    assert visitor.get('/docs').status_code == 404
    assert visitor.get('/openapi.json').status_code == 404
    assert visitor.post('/trial-access', data={'accessCode': code}).status_code == 403
    headers = {'Origin': ORIGIN}
    assert visitor.post('/trial-access', headers=headers, data={'accessCode': 'wrong'}).status_code == 401
    assert not visitor.cookies
    assert visitor.post('/trial-access', headers=headers, data={'accessCode': code}).status_code == 200
    assert visitor.cookies[COOKIE]
    assert visitor.get('/api/libraries').status_code == 200
    for _ in range(5):
        assert visitor.post('/trial-access', headers=headers, data={'accessCode': 'wrong'}).status_code == 401
    assert visitor.post('/trial-access', headers=headers, data={'accessCode': code}).status_code == 429
    rotated = client(app_at(tmp_path, access_code='rotated-secret-123456'))
    rotated.cookies.set(COOKIE, visitor.cookies[COOKIE])
    assert rotated.get('/api/libraries').status_code == 401


def test_request_body_limit_counts_chunks_before_handler_runs():
    import asyncio
    from backend.trial_body_limit import RequestBodyLimit

    called = []

    async def endpoint(scope, receive, send):
        called.append(True)

    async def exercise():
        for declared in ([], [(b'content-length', b'1')]):
            messages = iter([{'type': 'http.request', 'body': b'12345', 'more_body': True},
                             {'type': 'http.request', 'body': b'67890', 'more_body': False}])
            sent = []

            async def receive():
                return next(messages)

            async def send(message):
                sent.append(message)

            await RequestBodyLimit(endpoint, 6)({'type': 'http', 'method': 'POST', 'path': '/api/generation-tasks',
                                                'headers': declared}, receive, send)
            assert sent[0]['status'] == 413
        assert not called

    asyncio.run(exercise())


def test_resumable_upload_retains_offsets_and_creates_one_task(tmp_path, monkeypatch):
    import hashlib
    from backend import web_api
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    headers = {'Origin': ORIGIN}
    content = b'WHERE filters rows.\n' * 16000
    ident = 'c' * 32
    base = '/api/resumable-uploads/' + ident
    plan = {'libraryId': 'study', 'libraryName': 'Study', 'questionCount': 1,
            'files': [{'name': 'lesson.txt', 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}]}
    reply = browser.put(base, headers=headers, json=plan)
    assert reply.status_code == 200, reply.text
    assert reply.json()['offsets'] == [0]
    split = reply.json()['chunkBytes']
    first = content[:split]
    chunk_headers = {**headers, 'X-Chunk-SHA256': hashlib.sha256(first).hexdigest()}
    assert browser.put(base + '/files/0?offset=0', headers=chunk_headers, content=first).json()['offset'] == split
    assert browser.put(base + '/files/0?offset=0', headers=chunk_headers, content=first).json()['offset'] == split
    assert browser.post(base + '/complete', headers=headers).status_code == 409

    restarted = client(app_at(tmp_path))
    restarted.cookies.set(COOKIE, browser.cookies[COOKIE])
    assert restarted.put(base, headers=headers, json=plan).json()['offsets'] == [split]
    other = client(app)
    other.get('/')
    assert other.get(base).status_code == 404

    tail = content[split:]
    reply = restarted.put(base + f'/files/0?offset={split}', headers={
        **headers, 'X-Chunk-SHA256': hashlib.sha256(tail).hexdigest()}, content=tail)
    assert reply.json()['offset'] == len(content), reply.text
    complete = restarted.post(base + '/complete', headers=headers)
    assert complete.status_code == 200, complete.text
    assert restarted.post(base + '/complete', headers=headers).json()['taskId'] == complete.json()['taskId']
    assert len(restarted.get('/api/generation-tasks').json()['tasks']) == 1
    with next((tmp_path / 'data/spaces').glob('*/uploads/*.txt')).open('rb') as saved:
        assert saved.read() == content
    assert not list((tmp_path / 'data/spaces').glob('*/resumable/*.part'))


def test_resumable_upload_rejects_bad_chunks_and_recovers_uncommitted_tail(tmp_path):
    import hashlib
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    headers = {'Origin': ORIGIN}
    ident = 'd' * 32
    base = '/api/resumable-uploads/' + ident
    content = b'abcdef'
    plan = {'libraryId': 'study', 'libraryName': 'Study', 'questionCount': 1,
            'files': [{'name': 'lesson.txt', 'size': 6, 'sha256': hashlib.sha256(content).hexdigest()}]}
    assert browser.put(base, headers=headers, json=plan).status_code == 200
    assert browser.put(base, headers=headers, json={**plan, 'requirements': 'changed'}).status_code == 409
    assert browser.put(base + '/files/0?offset=0', headers={**headers, 'X-Chunk-SHA256': 'bad'}, content=b'abc').status_code == 422
    good = {**headers, 'X-Chunk-SHA256': hashlib.sha256(b'abc').hexdigest()}
    assert browser.put(base + '/files/0?offset=1', headers=good, content=b'abc').status_code == 409
    assert browser.put(base + '/files/0?offset=0', headers=good, content=b'abc').status_code == 200
    partial = next((tmp_path / 'data/spaces').glob('*/resumable/*.part'))
    with partial.open('ab') as target:
        target.write(b'uncommitted')
    last = {**headers, 'X-Chunk-SHA256': hashlib.sha256(b'def').hexdigest()}
    assert browser.put(base + '/files/0?offset=3', headers=last, content=b'def').json()['offset'] == 6
    assert partial.read_bytes() == content
    wrong = {**headers, 'X-Chunk-SHA256': hashlib.sha256(b'xyz').hexdigest()}
    assert browser.put(base + '/files/0?offset=0', headers=wrong, content=b'xyz').status_code == 409


def test_upload_receipt_recovers_and_deduplicates_retries(tmp_path, monkeypatch):
    from backend import web_api
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    fields = {'libraryId': 'study', 'libraryName': 'Study', 'questionCount': '1', 'clientRequestId': 'a' * 32}
    headers = {'Origin': ORIGIN}

    def upload(connection, value):
        return connection.post('/api/generation-tasks', headers=headers, data=value,
                               files={'files': ('lesson.txt', 'WHERE 子句按照条件筛选数据行。'.encode())})

    first = upload(browser, fields)
    assert first.status_code == 202, first.text
    replay = upload(browser, fields)
    assert replay.status_code == 202 and replay.json() == first.json(), replay.text
    receipt = '/api/generation-submissions/' + fields['clientRequestId']
    assert browser.get(receipt).json() == first.json()
    assert len(browser.get('/api/generation-tasks').json()['tasks']) == 1
    assert upload(browser, {**fields, 'requirements': 'different'}).status_code == 409
    assert upload(browser, {**fields, 'clientRequestId': 'bad'}).status_code == 422
    other = client(app)
    other.get('/')
    assert other.get(receipt).status_code == 404

    browser.post('/api/generation-tasks/' + first.json()['taskId'] + '/cancel', headers=headers)
    connections = [client(app), client(app)]
    for connection in connections:
        connection.cookies.update(browser.cookies)
    concurrent_fields = {**fields, 'clientRequestId': 'b' * 32}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda connection: upload(connection, concurrent_fields), connections))
    assert all(reply.status_code == 202 for reply in replies), [reply.text for reply in replies]
    assert replies[0].json()['taskId'] == replies[1].json()['taskId']
    assert len(browser.get('/api/generation-tasks').json()['tasks']) == 2
    assert len(list((tmp_path / 'data/spaces').glob('*/uploads/*.txt'))) == 2


def test_disconnected_upload_returns_response_without_creating_task():
    import asyncio
    from backend.trial_body_limit import RequestBodyLimit

    async def exercise():
        messages = iter([{'type': 'http.request', 'body': b'partial', 'more_body': True}, {'type': 'http.disconnect'}])
        responses = []

        async def endpoint(scope, receive, send):
            raise AssertionError('An incomplete body must not reach the upload handler')

        async def receive():
            return next(messages)

        async def send(message):
            responses.append(message)

        await RequestBodyLimit(endpoint, 100)({'type': 'http', 'method': 'POST', 'path': '/api/generation-tasks',
                                             'headers': []}, receive, send)
        assert responses[0]['status'] == 499

    asyncio.run(exercise())


def submit_recovery_task(browser, library='recovery'):
    browser.get('/')
    material = Path(__file__).resolve().parents[1] / 'test-materials' / 'SQL短文本资料.txt'
    response = browser.post('/api/generation-tasks', headers={'Origin': ORIGIN},
                            files={'files': ('sql.txt', material.read_bytes())},
                            data={'libraryId': library, 'libraryName': 'SQL',
                                  'requirements': '生成一道考查 WHERE 的单选题', 'questionCount': 1})
    assert response.status_code == 202, response.text
    return response.json()['taskId']


def browser_store(tmp_path, browser):
    space = browser.cookies[COOKIE].split('.')[0]
    return TrialStore(tmp_path / 'data' / 'spaces' / space)


def test_generation_recovers_queued_and_running_jobs_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    queued_browser, running_browser, cancelling_browser = (client(app) for _ in range(3))
    queued, running, cancelling = (submit_recovery_task(browser)
                                   for browser in (queued_browser, running_browser, cancelling_browser))
    running_store = browser_store(tmp_path, running_browser)
    assert running_store.claim()['id'] == running
    checkpoint = {'files': [{'name': 'sql.txt', 'status': 'parsing'}]}
    running_store.update(running, 'running', 'AI生成题目', checkpoint)
    assert browser_store(tmp_path, cancelling_browser).claim()['id'] == cancelling
    assert cancelling_browser.post(f'/api/generation-tasks/{cancelling}/cancel',
                                   headers={'Origin': ORIGIN}).status_code == 200

    def complete_queued(worker, job):
        assert job['id'] == queued
        worker.store.update(queued, 'failed', '测试处理完成', error='测试模型已处理原任务')

    monkeypatch.setattr(Runner, 'supervise', complete_queued)
    restarted = app_at(tmp_path, start_worker=True)
    with client(restarted) as browser:
        browser.cookies.update(running_browser.cookies)
        deadline = time.monotonic() + 5
        while running_store.get(running)['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(.02)
        # Simulate a stale worker attempting to write after recovery.
        running_store.update(running, 'succeeded', '旧进程回写', {'files': []})
        recovered = browser.get(f'/api/generation-tasks/{running}').json()
        assert recovered['status'] == 'interrupted'
        assert '可重试' in recovered['stage']
        assert recovered['files'] == checkpoint['files']
        browser.cookies.update(cancelling_browser.cookies)
        assert browser.get(f'/api/generation-tasks/{cancelling}').json()['status'] == 'cancelled'
        browser.cookies.update(queued_browser.cookies)
        while True:
            resumed = browser.get(f'/api/generation-tasks/{queued}').json()
            if resumed['status'] == 'failed' or time.monotonic() >= deadline:
                break
            time.sleep(.02)
        assert resumed['taskId'] == queued
        assert resumed['stage'] == '测试处理完成'


def test_generation_timeout_is_visible_and_can_be_retried(tmp_path, monkeypatch):
    import generate_from_file

    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    ident = submit_recovery_task(browser)
    store = browser_store(tmp_path, browser)
    job = store.claim()

    def model_timeout(*args, **kwargs):
        raise ReadTimeout('simulated Ollama read timeout')

    monkeypatch.setattr(generate_from_file, 'generate_questions', model_timeout)
    Runner(store).run(job)
    task = browser.get(f'/api/generation-tasks/{ident}').json()
    assert task['status'] == 'failed', task
    assert '等待本机模型响应超时' in task['error'], task
    retry = browser.post(f'/api/generation-tasks/{ident}/retry', headers={'Origin': ORIGIN})
    assert retry.status_code == 202, retry.text
    new = store.get(retry.json()['taskId'])
    assert new['request']['fileIds'] == job['request']['fileIds']
    duplicate = browser.post(f'/api/generation-tasks/{ident}/retry', headers={'Origin': ORIGIN})
    assert duplicate.status_code == 202
    assert duplicate.json() == retry.json()


def wait_for_cancellation(root, job):
    (Path(root) / 'child-started').touch()
    time.sleep(30)


def test_cancel_stops_active_child_and_keeps_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    browser = client(app_at(tmp_path))
    ident = submit_recovery_task(browser)
    store = browser_store(tmp_path, browser)
    job = store.claim()
    checkpoint = {'files': [{'name': 'sql.txt', 'status': 'parsing'}]}
    store.update(ident, 'running', 'AI生成题目', checkpoint)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(Runner(store).supervise, job, wait_for_cancellation)
        try:
            deadline = time.monotonic() + 10
            while not (store.root / 'child-started').exists() and time.monotonic() < deadline:
                time.sleep(.02)
            assert (store.root / 'child-started').exists()
        finally:
            response = browser.post(f'/api/generation-tasks/{ident}/cancel', headers={'Origin': ORIGIN})
            assert response.status_code == 200, response.text
        active.result(timeout=5)
    cancelled = browser.get(f'/api/generation-tasks/{ident}').json()
    assert cancelled['status'] == 'cancelled'
    assert cancelled['files'] == checkpoint['files']


def test_concurrent_retries_and_repeated_archiving_are_idempotent(tmp_path):
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    # The deterministic exam generator lets both requests reach a terminal state immediately.
    original = create_exam(browser, 'recovery').json()['taskId']
    path = f'/api/generation-tasks/{original}'
    peers = [client(app), client(app)]
    for peer in peers:
        peer.cookies.update(browser.cookies)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda peer: peer.post(path + '/retry', headers={'Origin': ORIGIN}), peers))
    assert all(response.status_code == 202 for response in responses), [r.text for r in responses]
    retried = responses[0].json()['taskId']
    assert retried != original
    assert responses[1].json()['taskId'] == retried
    assert len(browser.get('/api/generation-tasks').json()['tasks']) == 2

    restarted = client(app_at(tmp_path))
    restarted.cookies.update(browser.cookies)
    assert restarted.post(path + '/retry', headers={'Origin': ORIGIN}).json()['taskId'] == retried
    store = browser_store(tmp_path, restarted)
    with store.db() as db:
        saved = db.execute('SELECT question_id FROM web_questions WHERE library_id=? ORDER BY question_id',
                           ('recovery',)).fetchall()
    assert saved
    for _ in range(2):
        response = restarted.post(f'/api/generation-tasks/{retried}/save', headers={'Origin': ORIGIN})
        assert response.status_code == 200, response.text
    with store.db() as db:
        assert db.execute('SELECT question_id FROM web_questions WHERE library_id=? ORDER BY question_id',
                          ('recovery',)).fetchall() == saved
