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





def test_zh06_preflight_requires_local_preview_and_verified_session(tmp_path, monkeypatch):
    from backend import web_trial
    monkeypatch.setattr(web_trial, 'generation_readiness',
                        lambda: {'generationReady': True, 'requiredTextModel': 'qwen3:1.7b'})
    public = app_at(tmp_path / 'public')
    public_browser = client(public)
    public_browser.get('/')
    assert public_browser.get('/api/evaluation-preflight').status_code == 404

    frontend = tmp_path / 'frontend'
    (frontend / 'assets').mkdir(parents=True, exist_ok=True)
    (frontend / 'index.html').write_text('<title>Local evaluation</title>')
    origin = 'http://127.0.0.1:8095'
    local = create_app(tmp_path / 'local-data', frontend, origin, SECRET,
                       start_worker=False, local_preview=True)
    browser = TestClient(local, base_url=origin)
    assert browser.get('/api/evaluation-preflight').status_code == 401
    assert browser.get('/').status_code == 200
    ready = browser.get('/api/evaluation-preflight')
    assert ready.status_code == 200
    assert ready.json()['localPreview'] is True
    assert ready.json()['requiredTextModel'] == 'qwen3:1.7b'
    assert browser.get('/api/evaluation-preflight',
                       headers={'Origin': 'https://evil.example'}).status_code == 403
    monkeypatch.setattr(web_trial, 'generation_readiness',
                        lambda: {'generationReady': False, 'generationIssue': '模型未启动'})
    unavailable = browser.get('/api/evaluation-preflight')
    assert unavailable.status_code == 200
    assert unavailable.json()['generationReady'] is False


def test_zh06_evaluation_question_types_reach_intended_worker_contract(tmp_path, monkeypatch):
    """Actual trial route accepts four kinds; no Ollama or worker is started."""
    import json
    from backend import web_api
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    source = b'WHERE filters rows before grouping. HAVING filters grouped results. GROUP BY creates groups.'
    cases = (
        ('mnemonic', '请编口诀区分WHERE与HAVING', 'mnemonic'),
        ('reply', '请根据SQL资料解释WHERE与HAVING的区别', 'reply'),
        ('cloze', '请按资料填空：分组后筛选使用什么子句？', 'cloze'),
        ('single_choice', '请生成一道关于HAVING的四选一单选题', None),
        ('reply', '仅依据SQL资料说明TCP三次握手的序号如何变化，并标出原文依据。', 'reply'),
    )
    for kind, requirement, expected_study_kind in cases:
        visitor = client(app)
        assert visitor.get('/').status_code == 200
        assert visitor.put('/api/libraries/evalsql', headers={'Origin': ORIGIN},
                           json={'title': 'SQL evaluation'}).status_code == 200
        answer = visitor.post('/api/generation-tasks',
            headers={'Origin': ORIGIN},
            data={
                'libraryId': 'evalsql', 'libraryName': 'SQL evaluation',
                'requirements': requirement, 'questionCount': '1',
                'questionType': kind,
            },
            files={'files': ('sql.txt', source, 'text/plain')})
        assert answer.status_code == 202, (kind, answer.text)
        with browser_store(tmp_path, visitor).db() as db:
            job = db.execute('SELECT request FROM jobs WHERE id=?',
                             (answer.json()['taskId'],)).fetchone()
        request = json.loads(job['request'])
        assert request['requirements'] == requirement
        assert request['questionCount'] == 1
        assert request.get('studyKind') == expected_study_kind
        assert request['requireModelGeneration'] is True


def test_study_plan_requires_session_and_an_existing_library(tmp_path):
    app = app_at(tmp_path)
    visitor = client(app)
    assert visitor.get('/api/study-plans/study').status_code == 401
    visitor.get('/')
    assert visitor.get('/api/study-plans/study').status_code == 404
    assert visitor.get('/api/study-plans/bad.id').status_code == 422

    assert visitor.put('/api/libraries/study', headers={'Origin': ORIGIN},
                       json={'title': '数据库'}).status_code == 200
    response = visitor.get('/api/study-plans/study')
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan['status'] == 'needs_diagnosis'
    assert plan['next_action'] == 'prepare_diagnostic'
    assert plan['topics'] == []
    assert plan['visited_skills'] == ['get_weak_knowledge_points', 'plan_diagnostic']

    assert visitor.delete('/api/libraries/study', headers={'Origin': ORIGIN}).status_code == 200
    assert visitor.get('/api/study-plans/study').status_code == 404
    assert visitor.get('/api/study-plans/study', headers={'Origin': 'https://evil.test'}).status_code == 403


def test_study_plan_uses_only_verified_browser_space_and_never_writes(tmp_path):
    app = app_at(tmp_path)
    alice, bob = client(app), client(app)
    alice.get('/')
    bob.get('/')
    headers = {'Origin': ORIGIN}
    for browser in (alice, bob):
        assert browser.put('/api/libraries/sql', headers=headers,
                           json={'title': 'SQL'}).status_code == 200

    with browser_store(tmp_path, alice).db() as db:
        db.execute('''INSERT INTO web_point_progress
            (library_id, point_key, label, mastery, attempts, correct)
            VALUES ('sql', 'having', 'HAVING', 0.28, 4, 1)''')
    with browser_store(tmp_path, bob).db() as db:
        db.execute('''INSERT INTO web_point_progress
            (library_id, point_key, label, mastery, attempts, correct)
            VALUES ('sql', 'where', 'WHERE', 0.82, 5, 4)''')

    def snapshot(browser):
        with browser_store(tmp_path, browser).db() as db:
            return tuple(tuple(row) for row in db.execute(
                'SELECT * FROM web_point_progress ORDER BY point_key'))

    before_alice, before_bob = snapshot(alice), snapshot(bob)
    result_alice = alice.get('/api/study-plans/sql')
    result_bob = bob.get('/api/study-plans/sql')
    assert result_alice.status_code == result_bob.status_code == 200
    assert result_alice.json()['next_action'] == 'prepare_targeted_practice'
    assert result_alice.json()['topics'] == ['HAVING']
    assert result_bob.json()['next_action'] == 'prepare_review'
    assert result_bob.json()['topics'] == []
    from backend.agent_decision_audit import replay_study_trace
    for response in (result_alice, result_bob):
        assert replay_study_trace(response.json()['decision_trace'])['matched'] is True
        assert 'HAVING' not in str(response.json()['decision_trace'])
        assert 'WHERE' not in str(response.json()['decision_trace'])
    assert snapshot(alice) == before_alice
    assert snapshot(bob) == before_bob

    assert alice.put('/api/libraries/alice-only', headers=headers,
                     json={'title': '仅本人'}).status_code == 200
    assert bob.get('/api/study-plans/alice-only').status_code == 404


def test_study_plan_rejects_invalid_persisted_progress(tmp_path):
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    assert browser.put('/api/libraries/sql', headers={'Origin': ORIGIN},
                       json={'title': 'SQL'}).status_code == 200
    with browser_store(tmp_path, browser).db() as db:
        db.execute('''INSERT INTO web_point_progress
            (library_id, point_key, label, mastery, attempts, correct)
            VALUES ('sql', 'having', 'HAVING', 0.2, 1, 2)''')
    result = browser.get('/api/study-plans/sql')
    assert result.status_code == 409
    assert '学习进度' in result.json()['detail']



def test_study_executor_reuses_verified_source_and_queues_once(tmp_path, monkeypatch):
    from backend import web_trial
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    monkeypatch.setattr(web_trial, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    headers = {'Origin': ORIGIN}
    original = submit_recovery_task(browser, library='study')
    store = browser_store(tmp_path, browser)
    store.update(original, 'failed', '测试源文件任务已结束', error='测试环境不运行模型')
    with store.db() as db:
        db.execute('''INSERT INTO web_point_progress
            (library_id, point_key, label, mastery, attempts, correct)
            VALUES ('study', 'having', 'HAVING', 0.28, 4, 1)''')
    proposal = browser.get('/api/study-plans/study').json()
    assert proposal['next_action'] == 'prepare_targeted_practice'
    assert len(proposal['sourceFiles']) == 1
    body = {'revision': proposal['revision'],
            'sourceFileId': proposal['sourceFiles'][0]['id'],
            'clientRequestId': 'a' * 32, 'questionCount': 2}
    first = browser.post('/api/study-plans/study/execute', headers=headers, json=body)
    assert first.status_code == 202, first.text
    assert first.json()['status'] == 'queued'
    assert first.json()['reused'] is False
    retry = browser.post('/api/study-plans/study/execute', headers=headers, json=body)
    assert retry.status_code == 202
    assert retry.json()['taskId'] == first.json()['taskId']
    assert retry.json()['reused'] is True
    with store.db() as db:
        record = db.execute('SELECT * FROM jobs WHERE id=?', (first.json()['taskId'],)).fetchone()
        request = __import__('json').loads(record['request'])
        assert request['fileIds'] == [body['sourceFileId']]
        assert request['questionCount'] == 2
        assert 'HAVING' in request['requirements']
        assert request['requireModelGeneration'] is True
        assert db.execute('SELECT COUNT(*) FROM study_practice_dispatches').fetchone()[0] == 1
        assert db.execute('SELECT attempts,correct,mastery FROM web_point_progress WHERE library_id=?', ('study',)).fetchone()['mastery'] == 0.28


def test_study_executor_denies_other_space_and_removed_source(tmp_path, monkeypatch):
    from backend import web_trial
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    monkeypatch.setattr(web_trial, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    alice, bob = client(app), client(app)
    alice.get('/')
    bob.get('/')
    headers = {'Origin': ORIGIN}
    original = submit_recovery_task(alice, library='alice')
    browser_store(tmp_path, alice).update(original, 'failed', '测试结束')
    proposal = alice.get('/api/study-plans/alice').json()
    body = {'revision': proposal['revision'],
            'sourceFileId': proposal['sourceFiles'][0]['id'],
            'clientRequestId': 'b' * 32, 'questionCount': 1}
    assert bob.post('/api/study-plans/alice/execute', headers=headers, json=body).status_code == 404
    assert alice.post('/api/study-plans/alice/execute', json=body).status_code == 403
    assert alice.post('/api/study-plans/alice/execute', headers=headers,
                      json={**body, 'questionCount': 0}).status_code == 422
    assert alice.post('/api/study-plans/alice/execute', headers=headers,
                      json={**body, 'sourceFileId': 'c' * 32}).status_code == 404
    remove = alice.delete(
        '/api/libraries/alice/items/source/' + body['sourceFileId'],
        headers=headers,
    )
    assert remove.status_code == 200, remove.text
    assert alice.post('/api/study-plans/alice/execute', headers=headers, json=body).status_code == 404


def test_study_executor_prevents_stale_plan_and_reused_id_changes(tmp_path, monkeypatch):
    from backend import web_trial
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    monkeypatch.setattr(web_trial, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    headers = {'Origin': ORIGIN}
    task_id = submit_recovery_task(browser, library='study')
    store = browser_store(tmp_path, browser)
    store.update(task_id, 'failed', '测试结束')
    proposal = browser.get('/api/study-plans/study').json()
    payload = {'revision': proposal['revision'], 'sourceFileId': proposal['sourceFiles'][0]['id'],
               'clientRequestId': 'd' * 32, 'questionCount': 1}
    with store.db() as db:
        db.execute('''INSERT INTO web_point_progress
            (library_id, point_key, label, mastery, attempts, correct)
            VALUES ('study', 'where', 'WHERE', 0.38, 3, 1)''')
    stale = browser.post('/api/study-plans/study/execute', headers=headers, json=payload)
    assert stale.status_code == 409
    new_proposal = browser.get('/api/study-plans/study').json()
    payload['revision'] = new_proposal['revision']
    executed = browser.post('/api/study-plans/study/execute', headers=headers, json=payload)
    assert executed.status_code == 202, executed.text
    assert browser.post('/api/study-plans/study/execute', headers=headers,
                        json={**payload, 'questionCount': 2}).status_code == 409
    assert browser.get('/api/study-plans/study').json()['next_action'] == 'prepare_targeted_practice'


def test_study_executor_requires_original_file_and_model_readiness(tmp_path, monkeypatch):
    from backend import web_trial
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    headers = {'Origin': ORIGIN}
    task_id = submit_recovery_task(browser, library='study')
    store = browser_store(tmp_path, browser)
    store.update(task_id, 'failed', '测试结束')
    proposal = browser.get('/api/study-plans/study').json()
    payload = {'revision': proposal['revision'], 'sourceFileId': proposal['sourceFiles'][0]['id'],
               'clientRequestId': 'e' * 32, 'questionCount': 1}
    monkeypatch.setattr(web_trial, 'generation_readiness',
                        lambda: {'generationReady': False, 'generationIssue': '模型尚未启动'})
    unavailable = browser.post('/api/study-plans/study/execute', headers=headers, json=payload)
    assert unavailable.status_code == 503
    assert '模型尚未启动' in unavailable.text
    monkeypatch.setattr(web_trial, 'generation_readiness', lambda: {'generationReady': True})
    source = store.file(payload['sourceFileId'], 'web-local')
    Path(source['path']).unlink()
    response = browser.post('/api/study-plans/study/execute', headers=headers, json=payload)
    assert response.status_code == 409
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM study_practice_dispatches').fetchone()[0] == 0



def test_agent_evaluation_uses_real_task_metadata_not_model_claims(tmp_path, monkeypatch):
    import json
    from backend import web_trial
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    monkeypatch.setattr(web_trial, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    browser.get('/')
    headers = {'Origin': ORIGIN}
    original = submit_recovery_task(browser, library='sql')
    store = browser_store(tmp_path, browser)
    store.update(original, 'failed', '测试旧任务完成')
    proposal = browser.get('/api/study-plans/sql').json()
    payload = {
        'revision': proposal['revision'], 'sourceFileId': proposal['sourceFiles'][0]['id'],
        'clientRequestId': 'f'*32, 'questionCount': 2,
    }
    dispatched = browser.post('/api/study-plans/sql/execute', headers=headers, json=payload)
    assert dispatched.status_code == 202, dispatched.text
    task = dispatched.json()['taskId']
    queued = browser.get('/api/study-evaluation/sql')
    assert queued.status_code == 200
    data = queued.json()
    assert data['sampleCount'] == 1
    assert data['summary']['pendingCount'] == 1
    assert data['summary']['completedRate'] is None
    assert data['summary']['autoAcceptanceRatio'] is None
    assert data['runs'][0]['planAction'] == 'prepare_diagnostic'
    assert data['runs'][0]['generatedCandidates'] is None
    assert data['notMeasured'] == ['answerCorrectness', 'citationSupportRate',
                                    'humanUsability', 'agentDecisionQuality', 'llmTokenCost']

    # Artificial fixture is persisted as a task result, NOT a claimed live model run.
    fake_result = {
        'accepted': 2,
        'files': [{'generatedCandidates': 5, 'name': 'private-lesson.txt'}],
        'rejected': [
            {'status': 'rejected_or_needs_review',
             'reasons': ['private diagnostic reason: password=SHOULD_NOT_LEAK']},
            {'status': 'visual_unverified', 'question': 'do not expose original question'},
        ],
        'secretPrompt': 'do not expose original prompt',
    }
    with store.db() as db:
        db.execute(
            "UPDATE jobs SET state='succeeded',result=?,updated=created+3 WHERE id=?",
            (json.dumps(fake_result), task),
        )
        db.execute(
            "INSERT INTO job_events(job_id,state,stage,created) VALUES(?,?,?,?)",
            (task, 'running', 'AI生成题目 · 测试', 1.0),
        )
        db.execute(
            "INSERT INTO job_events(job_id,state,stage,created) VALUES(?,?,?,?)",
            (task, 'running', '根据质检原因重新生成', 2.0),
        )
    evaluated = browser.get('/api/study-evaluation/sql')
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    assert body['summary']['succeededCount'] == 1
    assert body['summary']['completedRate'] == 1
    assert body['summary']['measuredGeneratedCandidates'] == 5
    assert body['summary']['measuredAutoAccepted'] == 2
    assert body['summary']['autoAcceptanceRatio'] == .4
    assert body['runs'][0]['retryEvents'] == 1
    assert body['runs'][0]['generationEvents'] == 1
    assert body['runs'][0]['wallTimeMs'] == 3000
    assert body['runs'][0]['rejectionCategories'] == {
        'rejected_or_needs_review': 1, 'visual_unverified': 1,
    }
    assert 'private' not in evaluated.text
    assert 'password=' not in evaluated.text
    assert 'original question' not in evaluated.text
    assert 'SHOULD_NOT_LEAK' not in evaluated.text
    with store.db() as db:
        assert db.execute('SELECT state FROM jobs WHERE id=?', (task,)).fetchone()[0] == 'succeeded'


def test_agent_evaluation_rejects_other_spaces_and_deleted_libraries(tmp_path):
    app = app_at(tmp_path)
    alice, bob = client(app), client(app)
    assert alice.get('/api/study-evaluation/sql').status_code == 401
    alice.get('/')
    bob.get('/')
    headers = {'Origin': ORIGIN}
    assert alice.put('/api/libraries/sql', headers=headers,
                     json={'title': 'SQL'}).status_code == 200
    assert bob.get('/api/study-evaluation/sql').status_code == 404
    assert alice.get('/api/study-evaluation/sql').json()['sampleCount'] == 0
    assert alice.get('/api/study-evaluation/bad.id').status_code == 422
    assert alice.get('/api/study-evaluation/sql',
                     headers={'Origin': 'https://evil.test'}).status_code == 403
    assert alice.delete('/api/libraries/sql', headers=headers).status_code == 200
    assert alice.get('/api/study-evaluation/sql').status_code == 404


def test_agent_evaluation_migrates_existing_dispatch_receipts(tmp_path):
    from backend.study_practice_executor import ensure_execution_tables
    from backend.web_trial import TrialStore
    store = TrialStore(tmp_path / 'legacy-space')
    with store.db() as db:
        db.execute('''CREATE TABLE study_practice_dispatches (
            client_request_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            created REAL NOT NULL
        )''')
        db.execute(
            "INSERT INTO study_practice_dispatches VALUES(?,?,?,?)",
            ('a'*32, 'b'*32, 'c'*64, 1.0),
        )
        ensure_execution_tables(db)
        ensure_execution_tables(db)
        row = db.execute("SELECT client_request_id,plan_action FROM study_practice_dispatches").fetchone()
        assert row['client_request_id'] == 'a'*32
        assert row['plan_action'] == 'unknown'




def test_retry_hard_limit_is_atomic_and_preserves_first_receipt(tmp_path, monkeypatch):
    import sqlite3
    from backend.retry_guard import RETRY_DEPTH_ERROR
    monkeypatch.setattr(web_api, 'generation_readiness',
                        lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser, stranger = client(app), client(app)
    original = submit_recovery_task(browser, library='sql')
    stranger.get('/')
    store = browser_store(tmp_path, browser)
    store.update(original, 'failed', '模拟初次处理失败')
    endpoint = f'/api/generation-tasks/{original}/retry'
    first = browser.post(endpoint, headers={'Origin': ORIGIN})
    assert first.status_code == 202, first.text
    retry_id = first.json()['taskId']
    assert retry_id != original
    assert browser.post(endpoint, headers={'Origin': ORIGIN}).json() == first.json()
    assert stranger.post(endpoint, headers={'Origin': ORIGIN}).status_code == 404
    store.update(retry_id, 'failed', '模拟重试失败')
    blocked = browser.post(
        f'/api/generation-tasks/{retry_id}/retry', headers={'Origin': ORIGIN})
    assert blocked.status_code == 409, blocked.text
    assert '最多允许一次' in blocked.text
    assert 'traceback' not in blocked.text.lower()
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 2
        links = db.execute(
            'SELECT original_id,retry_id FROM web_task_retries').fetchall()
        assert [(r['original_id'], r['retry_id']) for r in links] == [(original, retry_id)]
        # Database guard cannot be bypassed by another write path.
        with __import__('pytest').raises(sqlite3.IntegrityError, match=RETRY_DEPTH_ERROR):
            db.execute(
                'INSERT INTO web_task_retries VALUES(?,?)',
                (retry_id, 'f'*32))
        with __import__('pytest').raises(sqlite3.IntegrityError, match=RETRY_DEPTH_ERROR):
            db.execute(
                'INSERT INTO web_task_retries VALUES(?,?)',
                ('c'*32, retry_id))
    assert browser.get(
        f'/api/generation-tasks/{retry_id}/recovery-advice'
    ).json()['remainingSuggestedRetries'] == 0


def test_retry_hard_limit_concurrent_clicks_reuse_one_task(tmp_path, monkeypatch):
    monkeypatch.setattr(web_api, 'generation_readiness',
                        lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    original = submit_recovery_task(browser, library='sql')
    store = browser_store(tmp_path, browser)
    store.update(original, 'failed', '模拟处理失败')
    copies = [client(app) for _ in range(3)]
    for copy in copies:
        copy.cookies.update(browser.cookies)
    def retry(connection):
        return connection.post(
            f'/api/generation-tasks/{original}/retry',
            headers={'Origin': ORIGIN},
        )
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(retry, copies))
    assert all(r.status_code == 202 for r in responses), [
        (r.status_code, r.text[:180]) for r in responses]
    ids = {r.json()['taskId'] for r in responses}
    assert len(ids) == 1
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM web_task_retries').fetchone()[0] == 1
    retry_id = ids.pop()
    store.update(retry_id, 'failed', '模拟二次失败')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rejected = list(pool.map(
            lambda connection: connection.post(
                f'/api/generation-tasks/{retry_id}/retry',
                headers={'Origin': ORIGIN}),
            copies))
    assert all(response.status_code == 409 for response in rejected)
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 2


def test_retry_guard_survives_store_reopen(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setattr(web_api, 'generation_readiness',
                        lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    original = submit_recovery_task(browser, library='sql')
    store = browser_store(tmp_path, browser)
    store.update(original, 'failed', '模拟超时')
    first = browser.post(
        f'/api/generation-tasks/{original}/retry', headers={'Origin': ORIGIN})
    assert first.status_code == 202, first.text
    retry_id = first.json()['taskId']
    # A new app instance initializes the same existing space without
    # dropping or weakening its current retry receipt / trigger.
    restored = client(app_at(tmp_path))
    restored.cookies.update(browser.cookies)
    with browser_store(tmp_path, restored).db() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name='limit_task_retry_depth'"
        ).fetchone()[0] == 1
        with __import__('pytest').raises(sqlite3.IntegrityError):
            db.execute('INSERT INTO web_task_retries VALUES(?,?)',
                       (retry_id, 'e'*32))
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM web_task_retries').fetchone()[0] == 1


def test_agent_recovery_advice_is_scoped_read_only_and_bounded(tmp_path, monkeypatch):
    from backend import web_trial
    monkeypatch.setattr(web_api, 'generation_readiness',
                        lambda: {'generationReady': True})
    app = app_at(tmp_path)
    alice, bob = client(app), client(app)
    alice.get('/')
    bob.get('/')
    task = submit_recovery_task(alice, library='sql')
    endpoint = f'/api/generation-tasks/{task}/recovery-advice'
    assert bob.get(endpoint).status_code == 404
    assert client(app).get(endpoint).status_code == 401
    assert alice.get('/api/generation-tasks/other/recovery-advice').status_code == 404
    assert alice.get(endpoint).json()['nextAction'] == 'wait'
    store = browser_store(tmp_path, alice)

    sensitive = 'secret-study-content-cannot-leak'
    store.update(task, 'failed', '模型生成错误 ' + sensitive,
                 result={'accepted': 0, 'files': [],
                         'rejected': [{'reasons': ['等待本机模型响应超时，请稍后重试。',
                                                  sensitive]}]},
                 error=sensitive)
    advised = alice.get(endpoint)
    assert advised.status_code == 200, advised.text
    data = advised.json()
    assert data['nextAction'] == 'retry_with_confirmation'
    assert data['requiresHumanConfirmation'] is True
    assert data['willExecuteAutomatically'] is False
    assert data['remainingSuggestedRetries'] == 1
    from backend.agent_decision_audit import replay_recovery_trace
    assert replay_recovery_trace(data['decisionTrace'])['matched'] is True
    assert sensitive not in str(data['decisionTrace'])
    assert sensitive not in advised.text
    assert data['existingRetryTaskId'] is None
    with store.db() as db:
        before = db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
    alice.get(endpoint)
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == before

    retry = alice.post(f'/api/generation-tasks/{task}/retry',
                       headers={'Origin': ORIGIN})
    assert retry.status_code == 202, retry.text
    retry_id = retry.json()['taskId']
    old = alice.get(endpoint).json()
    assert old['nextAction'] == 'open_existing_retry'
    assert old['existingRetryTaskId'] == retry_id
    store.update(retry_id, 'failed', '模型再次超时',
                 result={'accepted': 0, 'files': [],
                         'rejected': [{'reasons': ['等待本机模型响应超时，请稍后重试。']}]})
    newer = alice.get(f'/api/generation-tasks/{retry_id}/recovery-advice').json()
    assert newer['nextAction'] == 'manual_quality_review'
    assert newer['remainingSuggestedRetries'] == 0
    assert replay_recovery_trace(newer['decisionTrace'])['matched'] is True
    assert bob.get(f'/api/generation-tasks/{retry_id}/recovery-advice').status_code == 404


def test_agent_recovery_advice_missing_source_and_quality_reject(tmp_path, monkeypatch):
    monkeypatch.setattr(web_api, 'generation_readiness',
                        lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    task = submit_recovery_task(browser, library='sql')
    store = browser_store(tmp_path, browser)
    advice_url = f'/api/generation-tasks/{task}/recovery-advice'
    store.update(task, 'failed', '未通过自动质检',
                 result={'accepted': 0, 'files': [],
                         'rejected': [{'status': 'rejected_or_needs_review',
                                       'reasons': ['内容需要人工复核']}]})
    assert browser.get(advice_url).json()['nextAction'] == 'manual_quality_review'
    with store.db() as db:
        job = db.execute('SELECT request FROM jobs WHERE id=?', (task,)).fetchone()
        file_id = __import__('json').loads(job['request'])['fileIds'][0]
        source = db.execute('SELECT path FROM files WHERE id=?', (file_id,)).fetchone()
    Path(source['path']).unlink()
    response = browser.get(advice_url)
    assert response.status_code == 200
    assert response.json()['nextAction'] == 'replace_source'
    assert 'path' not in response.json()
    assert response.json()['willExecuteAutomatically'] is False


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


def test_phase34_timing_is_scoped_and_leaks_no_stage_text(tmp_path):
    from backend.job_timing import phase_from_stage
    app = app_at(tmp_path)
    first, second = client(app), client(app)
    first.get('/')
    second.get('/')
    response = create_exam(first, 'sql')
    assert response.status_code == 201, response.text
    task = response.json()['taskId']
    endpoint = f'/api/generation-tasks/{task}/timing'
    assert client(app).get(endpoint).status_code == 401
    assert second.get(endpoint).status_code == 404
    assert first.get('/api/generation-tasks/missing/timing').status_code == 404
    assert first.get(endpoint, headers={'Origin': 'https://evil.test'}).status_code == 403

    secret = 'PRIVATE-CREDENTIAL-NEVER-DISCLOSE'
    store = browser_store(tmp_path, first)
    store.update(task, 'running', '解析 '+secret+'.docx')
    store.update(task, 'running', 'AI生成题目 '+secret)
    store.update(task, 'failed', '失败 '+secret, error=secret)
    before = store.get(task)
    info = first.get(endpoint)
    assert info.status_code == 200, info.text
    body = info.json()
    assert body['taskId'] == task
    assert body['errorCategory'] == 'task_failed'
    assert body['queueWaitMs'] is None
    assert body['timingBasis'] == 'completed_checkpoint_intervals'
    assert body['terminalWallTimeMs'] is not None
    assert secret not in info.text
    assert '.docx' not in info.text
    assert phase_from_stage(secret) == 'other'
    assert store.get(task) == before


def test_phase34_claim_and_archive_checkpoint_are_atomic_and_measurable(tmp_path, monkeypatch):
    monkeypatch.setattr(web_api, 'generation_readiness', lambda: {'generationReady': True})
    app = app_at(tmp_path)
    browser = client(app)
    task = submit_recovery_task(browser, library='sql')
    store = browser_store(tmp_path, browser)
    claimed = store.claim()
    assert claimed['id'] == task
    store.update(task, 'running', 'AI生成题目')
    store.update(task, 'running', '自动质量初筛')
    store.update(task, 'succeeded', '已结束', {'content': {'libraries': []}})
    with store.db() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM job_events WHERE job_id=? AND stage='准备解析'",
            (task,),
        ).fetchone()[0] == 1
        assert db.execute(
            "SELECT COUNT(*) FROM job_archive_metrics WHERE job_id=?",
            (task,),
        ).fetchone()[0] == 1
        before = db.execute('SELECT COUNT(*) FROM job_events WHERE job_id=?', (task,)).fetchone()[0]
    response = browser.get(f'/api/generation-tasks/{task}/timing')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['queueWaitMs'] is not None
    assert body['archiveCallbackMs'] is not None
    assert body['archiveCallbackMs'] >= 0
    assert 'generation' in body['phaseElapsedMs']
    assert 'quality' in body['phaseElapsedMs']
    with store.db() as db:
        after = db.execute('SELECT COUNT(*) FROM job_events WHERE job_id=?', (task,)).fetchone()[0]
    assert before == after


def test_phase34_timing_analyzer_handles_clock_regression_without_private_data():
    from backend.job_timing import timing_report
    task = 'a'*32
    job = {'id': task, 'created': 100.0, 'updated': 112.0, 'state': 'interrupted'}
    empty = timing_report(job, [])
    assert empty['phaseElapsedMs'] == {}
    assert empty['queueWaitMs'] is None
    assert empty['errorCategory'] == 'task_interrupted'
    events = [
        {'state': 'running', 'stage': '准备解析', 'created': 106.0},
        {'state': 'running', 'stage': 'AI生成题目 CREDENTIAL-SECRET', 'created': 104.0},
        {'state': 'interrupted', 'stage': '中断 CREDENTIAL-SECRET', 'created': 112.0},
    ]
    report = timing_report(job, events)
    assert report['queueWaitMs'] == 6000
    assert report['phaseElapsedMs']['preparation'] == 0
    assert report['phaseElapsedMs']['generation'] == 6000
    assert 'CREDENTIAL-SECRET' not in str(report)


def test_phase34_recovery_advice_and_timing_diagnostics_remain_independent(tmp_path):
    app = app_at(tmp_path)
    browser = client(app)
    task = submit_recovery_task(browser, library='sql')
    store = browser_store(tmp_path, browser)
    store.update(task, 'failed', '出题失败')
    timing_before = browser.get(f'/api/generation-tasks/{task}/timing')
    advice_before = browser.get(f'/api/generation-tasks/{task}/recovery-advice')
    assert timing_before.status_code == advice_before.status_code == 200
    for _ in range(2):
        assert browser.get(f'/api/generation-tasks/{task}/timing').json() == timing_before.json()
        assert browser.get(f'/api/generation-tasks/{task}/recovery-advice').json() == advice_before.json()
    assert 'recovery' not in timing_before.text.lower()
