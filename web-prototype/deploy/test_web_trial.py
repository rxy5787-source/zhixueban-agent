import concurrent.futures

from fastapi.testclient import TestClient

from backend.web_trial import COOKIE_LIFETIME, MAX_JOBS_PER_SPACE, MAX_LIBRARIES_PER_SPACE, create_app


ORIGIN = 'https://trial.example.test'
SECRET = 'testing-secret-only-' * 2
COOKIE = '__Host-zhixue-trial'


def app_at(tmp_path, maximum=32, **options):
    frontend = tmp_path / 'public'
    (frontend / 'assets').mkdir(parents=True, exist_ok=True)
    (frontend / 'index.html').write_text('<title>Trial</title>')
    return create_app(tmp_path / 'data', frontend, ORIGIN, SECRET, maximum, start_worker=False, **options)


def client(app):
    return TestClient(app, base_url=ORIGIN)


def create_exam(browser, library):
    return browser.post('/api/exam-practice-tasks', headers={'Origin': ORIGIN}, json={
        'libraryId': library, 'libraryName': library, 'questionCount': 1, 'topic': 'complement',
    })


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
