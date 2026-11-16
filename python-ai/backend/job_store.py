import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from .config import DATA

class Store:
    def __init__(self, root=DATA):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / "uploads").mkdir(exist_ok=True)
        self.path = root / "jobs.sqlite3"
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,sha256 TEXT NOT NULL,size INTEGER NOT NULL,path TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,state TEXT NOT NULL,stage TEXT NOT NULL,request TEXT NOT NULL,result TEXT NOT NULL,error TEXT NOT NULL,cancel INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS job_events(id INTEGER PRIMARY KEY,job_id TEXT NOT NULL,state TEXT NOT NULL,stage TEXT NOT NULL,created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS events_job ON job_events(job_id,id);
            CREATE TABLE IF NOT EXISTS job_archive_metrics(
              job_id TEXT PRIMARY KEY, callback_elapsed_ms INTEGER NOT NULL,
              created REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner,created);
            CREATE TABLE IF NOT EXISTS model_call(id INTEGER PRIMARY KEY,job_id TEXT NOT NULL,phase TEXT NOT NULL,response TEXT NOT NULL,created REAL NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES('serviceId',?)", (str(uuid.uuid4()),))
            self.service_id = db.execute("SELECT value FROM settings WHERE key='serviceId'").fetchone()[0]
    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def record_call(self, job_id, phase, response):
        with self.db() as db:db.execute('INSERT INTO model_call(job_id,phase,response,created) VALUES(?,?,?,?)',(job_id,phase,json.dumps(response,ensure_ascii=False),time.time()))
    def add_file(self, owner, name, digest, size, path):
        ident = uuid.uuid4().hex
        with self.db() as db:
            db.execute("INSERT INTO files VALUES(?,?,?,?,?,?)", (ident,owner,name,digest,size,str(path)))
        return ident
    def file(self, ident, owner):
        with self.db() as db:
            row=db.execute("SELECT * FROM files WHERE id=? AND owner=?",(ident,owner)).fetchone()
            return dict(row) if row else None
    def create(self, owner, request):
        ident=uuid.uuid4().hex; now=time.time()
        with self.db() as db:
            db.execute("INSERT INTO jobs(id,owner,state,stage,request,result,error,created,updated) VALUES(?,?,'queued','等待处理',?,'{}','',?,?)", (ident,owner,json.dumps(request,ensure_ascii=False),now,now))
        return ident
    def get(self, ident, owner=None):
        with self.db() as db:
            row=db.execute("SELECT * FROM jobs WHERE id=?"+(" AND owner=?" if owner is not None else ""),(ident,owner) if owner is not None else (ident,)).fetchone()
        if not row:return None
        value=dict(row)
        for key in ('request','result'):value[key]=json.loads(value[key])
        return value
    def update_request(self, ident, request):
        with self.db() as db:db.execute("UPDATE jobs SET request=?,updated=? WHERE id=? AND state='running'",(json.dumps(request,ensure_ascii=False),time.time(),ident))
    def claim(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:return None
            now = time.time()
            db.execute("UPDATE jobs SET state='running',stage='准备解析',updated=? WHERE id=?",(now,row['id']))
            db.execute("INSERT INTO job_events(job_id,state,stage,created) VALUES(?,?,?,?)",
                       (row['id'],'running','准备解析',now))
        return self.get(row['id'])
    def recent(self, owner):
        with self.db() as db:
            rows=db.execute('SELECT id,state,stage,request,updated FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 20',(owner,)).fetchall()
        return [{'jobId':r['id'],'state':r['state'],'stage':r['stage'],'libraryName':json.loads(r['request']).get('libraryName',''),'updated':r['updated']} for r in rows]
    def update(self, ident, state, stage, result=None, error=''):
        with self.db() as db:
            now=time.time()
            # A child that survives a server crash must not overwrite recovery.
            condition = "WHERE id=? AND state NOT IN ('interrupted','cancelled')"
            if result is None:
                updated = db.execute("UPDATE jobs SET state=?,stage=?,error=?,updated=? " + condition,
                                     (state,stage,error,now,ident))
            else:
                updated = db.execute("UPDATE jobs SET state=?,stage=?,result=?,error=?,updated=? " + condition,
                                     (state,stage,json.dumps(result,ensure_ascii=False),error,now,ident))
            if not updated.rowcount:
                return
            if result is not None:
                started_ns = time.perf_counter_ns()
                self.publish_result(db,ident,state,result,now)
                if state in ('succeeded', 'partial') and type(self).publish_result is not Store.publish_result:
                    callback_ms = max(0, (time.perf_counter_ns() - started_ns) // 1_000_000)
                    db.execute("""INSERT INTO job_archive_metrics(job_id,callback_elapsed_ms,created)
                        VALUES(?,?,?) ON CONFLICT(job_id) DO UPDATE
                        SET callback_elapsed_ms=excluded.callback_elapsed_ms,
                            created=excluded.created""", (ident,callback_ms,now))
            db.execute('INSERT INTO job_events(job_id,state,stage,created) VALUES(?,?,?,?)',(ident,state,stage,now))
    def publish_result(self, db, ident, state, result, now):
        """Allow a store to publish its result in the same transaction."""
    def cancel(self, ident, owner):
        with self.db() as db:
            db.execute("UPDATE jobs SET cancel=1,stage=CASE WHEN state='queued' THEN '已取消' ELSE '正在取消，已保存结果会保留' END,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,updated=? WHERE id=? AND owner=? AND state IN ('queued','running')",(time.time(),ident,owner))
    def recover(self):
        with self.db() as db:
            db.execute("""UPDATE jobs
                SET state=CASE WHEN cancel=1 THEN 'cancelled' ELSE 'interrupted' END,
                    stage=CASE WHEN cancel=1 THEN '已取消，已保存结果保留' ELSE '服务重启，任务已中断，可重试' END,
                    error=CASE WHEN cancel=1 THEN '' ELSE '任务中断，已完成结果仍保留' END,
                    updated=?
                WHERE state='running'""", (time.time(),))
