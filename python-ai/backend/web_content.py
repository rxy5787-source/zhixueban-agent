"""Question eligibility and atomic publication into local Web libraries."""
import json

from . import exam_practice
from .job_store import Store
from .practice_quality import standalone_issue

OWNER = 'web-local'

def candidates(job):
    libraries=job['result'].get('content',{}).get('libraries',[])
    return libraries[0].get('items',[]) if libraries else []

def eligible(item):
    meta=item.get('ai',{})
    rule_verified=(meta.get('reviewStatus')=='rule_verified' and meta.get('reviewMethod')==exam_practice.METHOD)
    return ((meta.get('reviewStatus')=='auto_prechecked' or rule_verified) and meta.get('textOnly') is True
            and not meta.get('visualAssisted') and len(item.get('options',[]))==4
            and len(set(item['options']))==4 and all(isinstance(x,str) and x.strip() for x in item['options'])
            and item.get('answer') in ('A','B','C','D')
            and bool(item.get('prompt')) and bool(item.get('explanation')) and bool(item.get('points'))
            and not standalone_issue(item['prompt'],item['explanation'])
            and bool(meta.get('questionId')) and bool(meta.get('sourceFileId')))

def questions(job, library_id):
    return [dict(item,id=item['ai']['questionId'],libraryId=library_id,qualityStatus=item['ai']['reviewStatus'],visualValidationLimit='仅基于提取文字；OCR须对照原页核实' if item['ai'].get('extraction')=='ocr' else '')
            for item in candidates(job) if eligible(item)]

def removed_items(db,library_id):
    return {(row['kind'],row['item_id']) for row in db.execute(
        'SELECT kind,item_id FROM web_removed_items WHERE library_id=?',(library_id,))}

def visible_questions(job,library_id,removed):
    if ('set',job['id']) in removed:return []
    return [item for item in questions(job,library_id) if ('question',item['id']) not in removed]


def is_library_deleted(db, ident):
    return db.execute('SELECT 1 FROM web_deleted_libraries WHERE library_id=?', (ident,)).fetchone() is not None


def archive_questions(db, job, library_id, now, removed):
    accepted = visible_questions(job, library_id, removed)
    db.executemany('INSERT OR IGNORE INTO web_questions VALUES(?,?,?,?,?)', (
        (item['id'], library_id, job['id'], json.dumps(item, ensure_ascii=False), now) for item in accepted
    ))
    return len(accepted)


class WebStore(Store):
    def publish_result(self, db, ident, state, result, now):
        if state not in ('succeeded', 'partial'):
            return
        link = db.execute('''SELECT t.library_id FROM web_tasks t JOIN jobs j ON j.id=t.task_id
                             WHERE t.task_id=? AND j.owner=? AND j.cancel=0''', (ident, OWNER)).fetchone()
        if link and not is_library_deleted(db, link['library_id']):
            library_id = link['library_id']
            archive_questions(db, {'id': ident, 'result': result}, library_id, now, removed_items(db, library_id))

    def archive_previous_results(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            key = 'web-auto-archive-v1'
            if db.execute('SELECT 1 FROM settings WHERE key=?', (key,)).fetchone():
                return
            for row in db.execute('''SELECT j.id,j.result,j.updated,t.library_id FROM jobs j JOIN web_tasks t ON t.task_id=j.id
                WHERE j.owner=? AND j.state IN ('succeeded','partial') AND j.cancel=0
                AND NOT EXISTS (SELECT 1 FROM web_deleted_libraries d WHERE d.library_id=t.library_id)
                ORDER BY j.updated,j.id''', (OWNER,)):
                library_id = row['library_id']
                removed = removed_items(db, library_id)
                if ('task', row['id']) not in removed:
                    archive_questions(db, {'id': row['id'], 'result': json.loads(row['result'])}, library_id, row['updated'], removed)
            db.execute('INSERT INTO settings VALUES(?,?)', (key, 'done'))

