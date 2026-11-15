"""Job store behaviour that the worker and the Web API rely on."""

import pytest

from backend.job_store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def events(store, job_id):
    with store.db() as db:
        return [
            (row["state"], row["stage"])
            for row in db.execute(
                "SELECT state, stage FROM job_events WHERE job_id=? ORDER BY id", (job_id,)
            )
        ]


def test_new_job_is_queued_and_owner_scoped(store):
    job_id = store.create("alice", {"questionCount": 1})
    assert store.get(job_id)["state"] == "queued"
    assert store.get(job_id, "alice")["request"] == {"questionCount": 1}
    assert store.get(job_id, "bob") is None


def test_claim_hands_out_each_job_once_in_creation_order(store):
    first = store.create("alice", {})
    second = store.create("alice", {})
    assert store.claim()["id"] == first
    assert store.claim()["id"] == second
    assert store.claim() is None
    assert store.get(first)["state"] == "running"


def test_update_stores_result_and_records_an_event(store):
    job_id = store.create("alice", {})
    store.claim()
    store.update(job_id, "succeeded", "已结束", {"accepted": 1})
    job = store.get(job_id)
    assert (job["state"], job["result"]) == ("succeeded", {"accepted": 1})
    assert events(store, job_id) == [("succeeded", "已结束")]


def test_cancelling_a_queued_job_is_final(store):
    job_id = store.create("alice", {})
    store.cancel(job_id, "alice")
    assert store.get(job_id)["state"] == "cancelled"
    # A late update from a worker must not revive it.
    store.update(job_id, "running", "迟到的更新")
    assert store.get(job_id)["state"] == "cancelled"
    assert store.claim() is None


def test_only_the_owner_can_cancel(store):
    job_id = store.create("alice", {})
    store.cancel(job_id, "bob")
    assert store.get(job_id)["state"] == "queued"


def test_cancelling_a_running_job_sets_a_flag_and_keeps_it_running(store):
    job_id = store.create("alice", {})
    store.claim()
    store.cancel(job_id, "alice")
    job = store.get(job_id)
    assert job["state"] == "running"
    assert job["cancel"] == 1


def test_recover_interrupts_running_jobs_and_keeps_queued_ones(store):
    running = store.create("alice", {})
    queued = store.create("alice", {})
    store.claim()
    store.recover()
    assert store.get(running)["state"] == "interrupted"
    assert store.get(queued)["state"] == "queued"
    # An interrupted job ignores updates from a child that outlived the crash.
    store.update(running, "succeeded", "迟到的结果", {"accepted": 9})
    assert store.get(running)["state"] == "interrupted"
    assert store.get(running)["result"] == {}


def test_recover_finishes_a_cancellation_that_was_in_progress(store):
    job_id = store.create("alice", {})
    store.claim()
    store.cancel(job_id, "alice")
    store.recover()
    assert store.get(job_id)["state"] == "cancelled"


def test_files_are_owner_scoped(store, tmp_path):
    ident = store.add_file("alice", "notes.txt", "0" * 64, 10, tmp_path / "notes.txt")
    assert store.file(ident, "alice")["name"] == "notes.txt"
    assert store.file(ident, "bob") is None


def test_recent_lists_only_own_jobs_newest_first(store):
    older = store.create("alice", {"libraryName": "SQL"})
    newer = store.create("alice", {"libraryName": "操作系统"})
    store.create("bob", {"libraryName": "other"})
    names = [row["libraryName"] for row in store.recent("alice")]
    assert names == ["操作系统", "SQL"]
    assert {older, newer} == {row["jobId"] for row in store.recent("alice")}


def test_model_calls_are_recorded_per_job(store):
    job_id = store.create("alice", {})
    store.record_call(job_id, "review", {"message": {"content": "{}"}})
    with store.db() as db:
        rows = db.execute("SELECT phase FROM model_call WHERE job_id=?", (job_id,)).fetchall()
    assert [row["phase"] for row in rows] == ["review"]
