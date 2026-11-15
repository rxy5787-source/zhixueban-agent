"""Local Web practice history and Bayesian knowledge tracing."""

import json
import unicodedata
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field

INITIAL, GUESS, SLIP, LEARN = 0.25, 0.28, 0.10, 0.08


class Answer(BaseModel):
    questionId: str = Field(min_length=1, max_length=128)
    answer: Literal['A', 'B', 'C', 'D']


class Submission(BaseModel):
    sessionId: UUID
    answers: list[Answer] = Field(min_length=1, max_length=12)


def init_tables(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS web_practice_sessions(
            id TEXT PRIMARY KEY, library_id TEXT NOT NULL, task_id TEXT NOT NULL,
            answers TEXT NOT NULL, report TEXT NOT NULL, created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS web_practice_by_library ON web_practice_sessions(library_id, created);
        CREATE TABLE IF NOT EXISTS web_point_progress(
            library_id TEXT NOT NULL, point_key TEXT NOT NULL, label TEXT NOT NULL,
            mastery REAL NOT NULL, attempts INTEGER NOT NULL, correct INTEGER NOT NULL,
            PRIMARY KEY(library_id, point_key));
    ''')


def update_mastery(prior, correct):
    known = (1 - SLIP) if correct else SLIP
    unknown = GUESS if correct else (1 - GUESS)
    posterior = prior * known / (prior * known + (1 - prior) * unknown)
    return min(0.99, max(0.01, posterior + (1 - posterior) * LEARN))


def point_view(row):
    return {
        'point': row['label'],
        'observations': row['attempts'],
        'correct': row['correct'],
        'mastery': row['mastery'],
        'reviewPriority': row['mastery'] < 0.45,
    }


def save_session(db, submission, task_id, library_id, questions, now):
    session_id = str(submission.sessionId)
    payload = json.dumps([answer.model_dump() for answer in submission.answers])
    previous = db.execute(
        'SELECT * FROM web_practice_sessions WHERE id=?', (session_id,)
    ).fetchone()
    if previous:
        if previous['task_id'] != task_id or previous['answers'] != payload:
            raise HTTPException(409, '这次练习已提交，答案不能重复修改')
        return json.loads(previous['report'])

    if len({answer.questionId for answer in submission.answers}) != len(submission.answers):
        raise HTTPException(422, '每道题只能提交一次答案')
    by_id = {question['id']: question for question in questions}
    if any(answer.questionId not in by_id for answer in submission.answers):
        raise HTTPException(409, '题目已不可练习，请返回题目集重新开始')

    correct_count = 0
    points = {}
    for answer in submission.answers:
        question = by_id[answer.questionId]
        correct = answer.answer == question['answer']
        correct_count += correct
        labels = {
            unicodedata.normalize('NFKC', label).strip().casefold(): label
            for label in question['points']
        }
        for key, label in labels.items():
            if not key:
                continue
            if key not in points:
                old = db.execute(
                    'SELECT * FROM web_point_progress WHERE library_id=? AND point_key=?',
                    (library_id, key),
                ).fetchone()
                points[key] = (
                    dict(old) if old else dict(label=label, mastery=INITIAL, attempts=0, correct=0)
                )
                points[key].update(sessionAnswered=0, sessionCorrect=0)
            row = points[key]
            row['mastery'] = update_mastery(row['mastery'], correct)
            row['attempts'] += 1
            row['correct'] += correct
            row['sessionAnswered'] += 1
            row['sessionCorrect'] += correct

    db.executemany(
        '''INSERT INTO web_point_progress VALUES(?,?,?,?,?,?) ON CONFLICT(library_id,point_key)
        DO UPDATE SET mastery=excluded.mastery, attempts=excluded.attempts, correct=excluded.correct''',
        (
            (library_id, key, row['label'], row['mastery'], row['attempts'], row['correct'])
            for key, row in points.items()
        ),
    )
    report = {
        'sessionId': session_id,
        'taskId': task_id,
        'libraryId': library_id,
        'created': now,
        'answered': len(submission.answers),
        'correct': correct_count,
        'points': [
            dict(
                point_view(row),
                sessionAnswered=row['sessionAnswered'],
                sessionCorrect=row['sessionCorrect'],
            )
            for row in sorted(points.values(), key=lambda row: row['mastery'])
        ],
    }
    db.execute(
        'INSERT INTO web_practice_sessions VALUES(?,?,?,?,?,?)',
        (session_id, library_id, task_id, payload, json.dumps(report, ensure_ascii=False), now),
    )
    return report


def history(db, library_id):
    sessions = []
    query = '''SELECT s.report, l.title FROM web_practice_sessions s JOIN web_libraries l ON l.id=s.library_id
               WHERE l.id NOT IN (SELECT library_id FROM web_deleted_libraries)'''
    args = ()
    if library_id:
        query += ' AND l.id=?'
        args = (library_id,)
    for row in db.execute(query + ' ORDER BY s.created DESC,s.id DESC LIMIT 30', args):
        report = json.loads(row['report'])
        report.pop('points', None)
        sessions.append(dict(report, libraryName=row['title']))
    points = []
    if library_id:
        points = [
            point_view(row)
            for row in db.execute(
                '''SELECT * FROM web_point_progress
            WHERE library_id=? ORDER BY mastery,label''',
                (library_id,),
            )
        ]
    return {'sessions': sessions, 'points': points}
