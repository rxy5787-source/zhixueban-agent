from contextlib import closing
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.agent_api import from_environment
from backend.web_practice import init_tables, update_mastery


TOKEN = 'test-token-for-isolated-agent-space-only'
AUTHORIZED = {'Authorization': f'Bearer {TOKEN}'}
SPACE_A, SPACE_B = 'a' * 48, 'b' * 48
URL = '/api/agent/weak-knowledge'


def make_space(root, space, rows):
    directory = root / 'spaces' / space
    directory.mkdir(parents=True)
    with closing(sqlite3.connect(directory / 'jobs.sqlite3')) as db, db:
        db.executescript('''
            CREATE TABLE web_libraries(id TEXT PRIMARY KEY);
            CREATE TABLE web_deleted_libraries(library_id TEXT PRIMARY KEY);
            INSERT INTO web_libraries VALUES ('active'), ('deleted');
            INSERT INTO web_deleted_libraries VALUES ('deleted');
        ''')
        init_tables(db)
        db.executemany('INSERT INTO web_point_progress VALUES (?, ?, ?, ?, ?, ?)', rows)


@pytest.fixture
def agent(tmp_path, monkeypatch):
    make_space(tmp_path, SPACE_A, [
        ('active', 'second', '第二薄弱点', .35, 3, 1),
        ('active', 'first', '第一薄弱点', update_mastery(.25, False), 1, 0),
        ('active', 'threshold', '阈值边界', .45, 2, 1),
        ('active', 'unseen', '没有作答', .10, 0, 0),
        ('deleted', 'archived', '回收站内容', .01, 2, 0),
    ])
    make_space(tmp_path, SPACE_B, [('active', 'private', '另一个空间', .10, 1, 0)])
    monkeypatch.setenv('ZHIXUE_AGENT_TRIAL_DATA', str(tmp_path))
    monkeypatch.setenv('ZHIXUE_AGENT_TOKEN', TOKEN)
    monkeypatch.setenv('ZHIXUE_AGENT_SPACE_ID', SPACE_A)
    monkeypatch.setenv('ZHIXUE_AGENT_USER_ID', 'test-learner')
    return TestClient(from_environment())


def test_returns_sorted_weak_points_with_stable_ids(agent):
    response = agent.get(URL, headers=AUTHORIZED)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    body = response.json()
    assert body['user_id'] == 'test-learner'
    points = body['weak_knowledge']
    assert [point['name'] for point in points] == ['第一薄弱点', '第二薄弱点']
    assert [point['mastery'] for point in points] == [update_mastery(.25, False), .35]
    assert points[0]['knowledge_id'] != points[1]['knowledge_id']
    assert agent.get(URL, headers=AUTHORIZED, params={'limit': 1}).json()['weak_knowledge'] == points[:1]


@pytest.mark.parametrize('limit', [0, 21, 'bad'])
def test_validates_limit(agent, limit):
    assert agent.get(URL, headers=AUTHORIZED, params={'limit': limit}).status_code == 422


@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer wrong'}])
def test_requires_valid_token(agent, headers):
    response = agent.get(URL, headers=headers)
    assert response.status_code == 401
    assert response.headers['WWW-Authenticate'] == 'Bearer'


@pytest.mark.parametrize('params', [{'user_id': 'other-learner'}, {'space_id': SPACE_B}])
def test_rejects_cross_space_access(agent, params):
    assert agent.get(URL, headers=AUTHORIZED, params=params).status_code == 403


def test_reads_only_the_space_bound_to_the_token(agent, monkeypatch):
    assert '另一个空间' not in agent.get(URL, headers=AUTHORIZED).text
    monkeypatch.setenv('ZHIXUE_AGENT_SPACE_ID', SPACE_B)
    other = TestClient(from_environment())
    assert [row['name'] for row in other.get(URL, headers=AUTHORIZED).json()['weak_knowledge']] == ['另一个空间']


def test_empty_space_returns_empty_json(agent, monkeypatch):
    import os
    from pathlib import Path

    empty = 'c' * 48
    make_space(Path(os.environ['ZHIXUE_AGENT_TRIAL_DATA']), empty, [])
    monkeypatch.setenv('ZHIXUE_AGENT_SPACE_ID', empty)
    response = TestClient(from_environment()).get(URL, headers=AUTHORIZED)
    assert response.status_code == 200
    assert response.json()['weak_knowledge'] == []


@pytest.mark.parametrize('failure', ['missing', 'corrupt'])
def test_database_failure_returns_503_without_creating_database(agent, tmp_path, failure):
    database = tmp_path / 'spaces' / SPACE_A / 'jobs.sqlite3'
    if failure == 'missing':
        database.unlink()
    else:
        database.write_bytes(b'Not a SQLite database')
    response = agent.get(URL, headers=AUTHORIZED)
    assert response.status_code == 503
    assert response.json() == {'detail': '学习数据暂不可读取'}
    assert database.exists() == (failure == 'corrupt')
