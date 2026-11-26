"""Phase 01 HTTP boundary tests run against the packaged backend."""
import json
import hashlib
import hmac
import logging
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from backend import web_api
from backend.web_trial import TrialStore, create_app
from backend import web_trial

ORIGIN = 'https://harness.test'
SECRET = 'harness-test-secret-' * 3
COOKIE = '__Host-zhixue-trial'


def application(tmp_path):
    frontend = tmp_path / 'public'
    (frontend / 'assets').mkdir(parents=True, exist_ok=True)
    (frontend / 'index.html').write_text('<title>Harness test</title>')
    return create_app(tmp_path / 'data', frontend, ORIGIN, SECRET, start_worker=False)


def test_evaluation_preflight_only_with_verified_loopback_session(tmp_path, monkeypatch):
    target = '/api/evaluation-preflight'
    public = TestClient(application(tmp_path), base_url=ORIGIN, client=('127.0.0.1', 8000))
    assert public.get('/').status_code == 200
    assert public.get(target).status_code == 404
    local_origin = 'http://127.0.0.1:18362'
    app = create_app(tmp_path / 'local', tmp_path / 'public', local_origin, SECRET,
                     start_worker=False, local_preview=True)
    monkeypatch.setattr(web_trial, 'generation_readiness', lambda: {'generationReady': True})
    local = TestClient(app, base_url=local_origin, client=('127.0.0.1', 8000))
    assert local.get(target).status_code == 401
    assert local.get('/').status_code == 200
    assert local.get(target).json() == {'localPreview': True, 'generationReady': True}
    other = TestClient(app, base_url=local_origin, client=('192.0.2.1', 8000))
    other.cookies.update(local.cookies)
    assert other.get(target).status_code == 404


def test_timing_requires_current_space_and_does_not_leak_raw_stages(tmp_path):
    app = application(tmp_path)
    with TestClient(app, base_url=ORIGIN) as first, TestClient(app, base_url=ORIGIN) as second:
        assert first.get('/api/generation-tasks/' + 'a' * 32 + '/timing').status_code == 401
        for browser in (first, second):
            assert browser.get('/').status_code == 200
        response = first.post('/api/exam-practice-tasks', headers={'Origin': ORIGIN}, json={
            'libraryId': 'shared-name', 'libraryName': 'Study', 'questionCount': 1, 'topic': 'complement'})
        assert response.status_code == 201
        ident = response.json()['taskId']
        store = TrialStore(tmp_path / 'data/spaces' / first.cookies[COOKIE].split('.')[0])
        with store.db() as db:
            db.execute('INSERT INTO job_events(job_id,state,stage,created) VALUES(?,?,?,?)',
                       (ident, 'running', '解析 PRIVATE_DOCUMENT_BEARER', time.time()))
        path = f'/api/generation-tasks/{ident}/timing'
        report = first.get(path)
        assert report.status_code == 200 and report.headers['cache-control'] == 'no-store'
        assert 'PRIVATE' not in report.text
        assert second.get(path).status_code == 404
        assert first.get('/api/generation-tasks').json()['tasks'][0]['taskId'] == ident


@pytest.mark.parametrize('mutation', ['tampered', 'expired'])
def test_invalid_signed_cookie_is_denied_without_data_creation(tmp_path, mutation):
    app = application(tmp_path)
    with TestClient(app, base_url=ORIGIN) as browser:
        browser.get('/')
        valid = browser.cookies[COOKIE]
        fields = valid.split('.')
        if mutation == 'tampered':
            fields[-1] = ('0' if fields[-1][0] != '0' else '1') + fields[-1][1:]
        else:
            fields[1] = '1'
            fields[2] = hmac.new(SECRET.encode(), '.'.join(fields[:2]).encode(), hashlib.sha256).hexdigest()
        browser.cookies.set(COOKIE, '.'.join(fields))
        before = sorted((tmp_path / 'data/spaces').iterdir())
        assert browser.get('/api/libraries').status_code == 401
        assert sorted((tmp_path / 'data/spaces').iterdir()) == before


@pytest.mark.parametrize('error_type', [RuntimeError, sqlite3.IntegrityError])
def test_internal_errors_and_logs_hide_exception_text(tmp_path, caplog, error_type):
    caplog.set_level(logging.INFO, logger='zhixue.operations')
    app = application(tmp_path)
    @app.get('/api/test-fault')
    def fault():
        raise error_type('PRIVATE_PATH_AND_CREDENTIAL')
    with TestClient(app, base_url=ORIGIN) as browser:
        browser.get('/')
        response = browser.get('/api/test-fault', headers={'X-Request-ID': 'PRIVATE_CLIENT_ID'})
        assert response.status_code == 500
        assert response.headers['cache-control'] == 'no-store'
        assert 'PRIVATE' not in response.text
        request_id = response.headers['x-request-id']
        assert len(request_id) == 32 and 'PRIVATE' not in request_id
    assert 'PRIVATE' not in caplog.text
    assert request_id in caplog.text


def test_validation_does_not_echo_private_input(tmp_path):
    with TestClient(application(tmp_path), base_url=ORIGIN) as browser:
        browser.get('/')
        response = browser.post('/api/exam-practice-tasks', headers={'Origin': ORIGIN}, json={
            'libraryId': 'a', 'libraryName': 'Study', 'questionCount': 'PRIVATE_INPUT', 'topic': 'complement'})
        assert response.status_code == 422 and 'PRIVATE' not in response.text
