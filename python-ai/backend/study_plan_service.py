"""Read-only study planning against an already selected, session-scoped library.

The caller MUST supply a connection from the verified current browser space.
A client-provided library ID alone is not an authorization token.
"""
from __future__ import annotations

import re
import sqlite3

from fastapi import HTTPException

from . import web_practice
from .study_skill_planner import StudyPlan, plan_study_from_progress


_LIBRARY_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


def plan_for_library(db: sqlite3.Connection, library_id: str) -> StudyPlan:
    """Read existing BKT progress; do not generate questions or change records.

    The HTTP session handler must obtain `db` from the authenticated browser's
    TrialStore. Never open a path or store selected by the request body or LLM.
    """
    if not isinstance(library_id, str) or not _LIBRARY_ID.fullmatch(library_id):
        raise HTTPException(422, "知识库ID格式无效")

    visible = db.execute(
        """SELECT 1 FROM web_libraries
           WHERE id = ?
           AND NOT EXISTS (
             SELECT 1 FROM web_deleted_libraries WHERE library_id = ?
           )""",
        (library_id, library_id),
    ).fetchone()
    if visible is None:
        # Do not distinguish missing and removed libraries.
        raise HTTPException(404, "知识库不存在")

    progress = web_practice.history(db, library_id)["points"]
    try:
        return plan_study_from_progress(progress)
    except ValueError as exc:
        # Invalid persisted evidence must not silently produce advice.
        raise HTTPException(409, "学习进度数据异常，暂时无法制定计划") from exc
