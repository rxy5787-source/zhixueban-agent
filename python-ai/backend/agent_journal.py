"""Durable checkpoints in the existing job database."""
from dataclasses import dataclass
import hashlib
import json
from uuid import uuid4


class JournalConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class Attempt:
    job_id: str
    token: str


class AgentJournal:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS agent_checkpoints (
                job_id TEXT PRIMARY KEY REFERENCES jobs(id),
                fingerprint TEXT NOT NULL, attempt TEXT NOT NULL, snapshot TEXT NOT NULL
            )""")

    def begin(self, context, goal, catalog, max_turns, model_key):
        """The host owns job claiming. A new attempt fences off previous writers."""
        if not context.job_id or context.root.resolve() != self.store.root.resolve():
            raise JournalConflict('unavailable_job')
        ident = context.job_id
        payload = [1, goal, context.owner, context.library_id, sorted(context.file_ids),
                   sorted(context.capabilities), catalog, max_turns, model_key]
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        token = uuid4().hex
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT state,cancel FROM jobs WHERE id=? AND owner=?',
                             (ident, context.owner)).fetchone()
            if not job or job['state'] != 'running' or job['cancel']:
                raise JournalConflict('unavailable_job')
            row = db.execute('SELECT fingerprint,snapshot FROM agent_checkpoints WHERE job_id=?',
                             (ident,)).fetchone()
            if row is None:
                db.execute('INSERT INTO agent_checkpoints VALUES (?,?,?,?)', (ident, fingerprint, token, '{}'))
                return Attempt(ident, token), {}
            if row['fingerprint'] != fingerprint:
                raise JournalConflict('incompatible_checkpoint')
            db.execute('UPDATE agent_checkpoints SET attempt=? WHERE job_id=?', (token, ident))
            return Attempt(ident, token), json.loads(row['snapshot'])

    def save(self, attempt, snapshot):
        with self.store.db() as db:
            changed = db.execute('''UPDATE agent_checkpoints SET snapshot=? WHERE job_id=? AND attempt=?
                AND EXISTS (SELECT 1 FROM jobs WHERE id=? AND state='running' AND cancel=0)''',
                (json.dumps(snapshot, ensure_ascii=False), attempt.job_id, attempt.token, attempt.job_id))
            if changed.rowcount != 1:
                raise JournalConflict('inactive_attempt')

    def inactive(self, attempt):
        with self.store.db() as db:
            row = db.execute('''SELECT 1 FROM jobs JOIN agent_checkpoints ON agent_checkpoints.job_id=jobs.id
                WHERE jobs.id=? AND attempt=? AND state='running' AND cancel=0''',
                             (attempt.job_id, attempt.token)).fetchone()
        return row is None

    def requeue(self, job_id, owner):
        """Return an interrupted Agent job to the existing queue under its original ID."""
        with self.store.db() as db:
            changed = db.execute('''UPDATE jobs SET state='queued', stage='等待恢复', error=''
                WHERE id=? AND owner=? AND state IN ('interrupted','failed') AND cancel=0
                AND EXISTS (SELECT 1 FROM agent_checkpoints WHERE job_id=jobs.id)''', (job_id, owner))
        return changed.rowcount == 1
