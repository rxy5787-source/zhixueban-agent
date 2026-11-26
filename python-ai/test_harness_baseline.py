"""Phase 01: real temporary SQLite and privacy assertions, no model inference."""
import json
import logging

import pytest

from backend.job_store import Store
from backend.job_timing import timing_report
from backend.observability import event


def test_claim_and_callback_metrics_are_committed_with_the_result(tmp_path):
    class PublishingStore(Store):
        def publish_result(self, db, ident, state, result, now):
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('published', ident))

    store = PublishingStore(tmp_path)
    ident = store.create('owner', {})
    assert store.claim()['id'] == ident
    store.update(ident, 'succeeded', '已结束', {'private': 'PRIVATE_EVIDENCE'})
    with store.db() as db:
        assert db.execute('SELECT stage FROM job_events ORDER BY id LIMIT 1').fetchone()[0] == '准备解析'
        assert db.execute('SELECT callback_elapsed_ms FROM job_archive_metrics WHERE job_id=?', (ident,)).fetchone()[0] >= 0
        assert db.execute("SELECT value FROM settings WHERE key='published'").fetchone()[0] == ident


def test_failed_publication_rolls_back_status_metrics_and_side_effect(tmp_path):
    class FailingStore(Store):
        def publish_result(self, db, ident, state, result, now):
            db.execute('INSERT INTO settings VALUES(?,?)', ('must_rollback', ident))
            raise RuntimeError('PRIVATE_DATABASE_VALUE')

    store = FailingStore(tmp_path)
    ident = store.create('owner', {})
    store.claim()
    with pytest.raises(RuntimeError):
        store.update(ident, 'succeeded', '已结束', {})
    assert store.get(ident)['state'] == 'running'
    with store.db() as db:
        assert not db.execute("SELECT 1 FROM settings WHERE key='must_rollback'").fetchone()
        assert not db.execute('SELECT 1 FROM job_archive_metrics').fetchone()


def test_logs_never_serialize_private_stage_error_or_model_content(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger='zhixue.operations')
    store = Store(tmp_path)
    ident = store.create('PRIVATE_OWNER', {})
    store.claim()
    store.update(ident, 'failed', '解析 PRIVATE_FILENAME', error='PRIVATE_EXCEPTION')
    store.record_call(ident, 'PRIVATE_PHASE', {'message': {'content': 'PRIVATE_MODEL'}, 'total_duration': 3_000_000})
    event('checkpoint', job_id='PRIVATE_ID', state='PRIVATE_STATE', phase='PRIVATE_PHASE', error_code='PRIVATE_ERROR')
    records = [json.loads(record.message) for record in caplog.records if record.name == 'zhixue.operations']
    assert records and all('PRIVATE' not in json.dumps(row) for row in records)
    assert any(row.get('jobId') == ident for row in records)
    assert any(row.get('elapsedMs') == 3 for row in records)


def test_timing_preserves_unknown_legacy_data_and_nonnegative_intervals():
    job = {'id': 'a' * 32, 'state': 'failed', 'created': 10, 'updated': 15}
    legacy = timing_report(job, [])
    assert legacy['queueWaitMs'] is None and legacy['archiveCallbackMs'] is None
    assert legacy['terminalWallTimeMs'] == 5000
    events = [{'state': 'running', 'stage': '准备解析', 'created': 12},
              {'state': 'running', 'stage': '解析 PRIVATE_FILE', 'created': 11},
              {'state': 'failed', 'stage': 'PRIVATE_ERROR', 'created': 15}]
    measured = timing_report(job, events)
    assert measured['queueWaitMs'] == 2000
    assert all(row['elapsedMs'] >= 0 for row in measured['phaseIntervals'])
    assert 'PRIVATE' not in json.dumps(measured)


def test_unknown_log_events_are_rejected():
    with pytest.raises(ValueError):
        event('PRIVATE_NEW_EVENT')
