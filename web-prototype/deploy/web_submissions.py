"""Receipts let an interrupted upload response be recovered without duplicate jobs."""

from fastapi import HTTPException


def init_tables(db):
    db.execute('''CREATE TABLE IF NOT EXISTS web_submissions(
        request_id TEXT PRIMARY KEY, task_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL)''')


def find(db, request_id, fingerprint=None):
    row = db.execute('''SELECT s.task_id, s.fingerprint, j.state FROM web_submissions s
        JOIN jobs j ON j.id=s.task_id WHERE s.request_id=?''', (request_id,)).fetchone()
    if row is None:
        return None
    if fingerprint is not None and row['fingerprint'] != fingerprint:
        raise HTTPException(409, '本次提交标识已用于其他资料或要求，请重新提交。')
    return {'taskId': row['task_id'], 'status': row['state']}
