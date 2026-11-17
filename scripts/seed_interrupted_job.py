"""Insert one synthetic crash checkpoint in an OFFLINE, stopped test container volume.

CI invokes this fixture between removing one Docker container and replacing
it with another. Never point it at real or shared user data.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time


def seed(spaces: Path, state_file: Path) -> str:
    data = json.loads(state_file.read_text(encoding="utf-8"))
    space = data["alphaSpace"]
    if not re.fullmatch(r"[a-f0-9]{48}", space):
        raise ValueError("Invalid synthetic browser space")
    if spaces.is_symlink() or state_file.is_symlink():
        raise ValueError("Symlinked fixture path refused")
    db_path = spaces / space / "jobs.sqlite3"
    if not db_path.is_file() or db_path.is_symlink():
        raise ValueError("Expected a pre-existing offline test space database")
    task = secrets.token_hex(16)
    now = time.time()
    request = {
        "fileIds": [], "libraryName": "通用学习资料 alpha", "subject": "资料学习",
        "questionCount": 1, "requirements": "通用知识复习",
        "requireModelGeneration": True, "visionFallback": False,
    }
    checkpoint = {"files": [{"name": "synthetic.txt", "status": "parsing"}]}
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        library = conn.execute(
            "SELECT 1 FROM web_libraries WHERE id='phase45-alpha'"
        ).fetchone()
        if not library:
            raise ValueError("Test library has not been created")
        if conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]:
            raise ValueError("Offline fixture requires an empty synthetic task table")
        conn.execute(
            """INSERT INTO jobs (id,owner,state,stage,request,result,error,created,updated)
               VALUES (?,'web-local','running','AI生成题目',? ,?, '',?,?)""",
            (task, json.dumps(request,ensure_ascii=False),
             json.dumps(checkpoint,ensure_ascii=False), now, now))
        conn.execute("INSERT INTO web_tasks (task_id,library_id) VALUES (?,'phase45-alpha')",
                     (task,))
        conn.execute(
            "INSERT INTO job_events(job_id,state,stage,created) VALUES (?,?,?,?)",
            (task,"running","AI生成题目",now))
    data["taskId"] = task
    state_file.write_text(json.dumps(data,sort_keys=True), encoding="utf-8")
    state_file.chmod(0o600)
    print("PASS: one synthetic running-task checkpoint inserted into stopped Docker volume")
    return task


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: seed_interrupted_job.py SPACES_DIR STATE_JSON", file=sys.stderr)
        return 2
    seed(Path(argv[1]), Path(argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
