"""Privacy-minimizing, read-only operational metrics for confirmed Agent practice.

Only counts, vetted enum statuses, and timestamps leave the current browser
space. Never select or serialize model_call.response, source text, prompts,
answers, rejected reasons, or user files. This is NOT a content-accuracy grade.
"""
from __future__ import annotations

import json
from collections import Counter

from .study_plan_service import require_study_library
from .web_content import OWNER

TERMINAL = frozenset({"succeeded", "partial", "failed", "cancelled", "interrupted"})
KNOWN_STATES = TERMINAL | {"queued", "running"}
ACTIONS = frozenset({"prepare_diagnostic", "prepare_targeted_practice", "prepare_review"})
REJECTION_CATEGORIES = frozenset({
    "rejected_or_needs_review", "text_unreadable", "visual_unverified",
})


def _json_object(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _nonnegative_integer(value):
    return value if type(value) is int and value >= 0 else None


def _wall_time_ms(row) -> int | None:
    if row["state"] not in TERMINAL:
        return None
    return max(0, round(1000 * (row["updated"] - row["created"])))


def _job_metrics(db, row) -> dict:
    request = _json_object(row["request"])
    result = _json_object(row["result"])
    files = result.get("files")
    file_counts = []
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict):
                count = _nonnegative_integer(item.get("generatedCandidates"))
                if count is not None:
                    file_counts.append(count)
    generated = sum(file_counts) if file_counts else None

    # Stored accepted value is a machine precheck count, not a human-graded label.
    accepted = _nonnegative_integer(result.get("accepted"))
    rejected = result.get("rejected")
    rejected_entries = len(rejected) if isinstance(rejected, list) else None
    reasons_by_category = Counter()
    if isinstance(rejected, list):
        for item in rejected:
            if not isinstance(item, dict):
                reasons_by_category["unspecified"] += 1
                continue
            category = item.get("status")
            safe_category = category if isinstance(category, str) and category in REJECTION_CATEGORIES else "unspecified"
            reasons_by_category[safe_category] += 1

    events = db.execute(
        "SELECT state,stage,created FROM job_events WHERE job_id=? ORDER BY id",
        (row["task_id"],),
    ).fetchall()
    attempts = sum(
        event["stage"].startswith(("AI生成题目", "AI生成"))
        for event in events if isinstance(event["stage"], str)
    )
    retries = sum(
        event["stage"].startswith("根据质检原因重新生成")
        for event in events if isinstance(event["stage"], str)
    )
    start = next((event["created"] for event in events if event["state"] == "running"), None)
    queue_ms = (
        max(0, round(1000 * (start - row["created"]))) if start is not None else None
    )

    status = row["state"] if row["state"] in KNOWN_STATES else "unknown"
    action = row["plan_action"] if row["plan_action"] in ACTIONS else "unknown"
    requested = _nonnegative_integer(request.get("questionCount"))
    acceptance = (
        round(accepted / generated, 4)
        if generated is not None and generated > 0 and accepted is not None
        and accepted <= generated else None
    )
    return {
        "taskId": row["task_id"],
        "planAction": action,
        "status": status,
        "requestedCount": requested,
        "generatedCandidates": generated,
        "autoAcceptedCount": accepted,
        "rejectedRecords": rejected_entries,
        "rejectionCategories": dict(sorted(reasons_by_category.items())),
        "generationEvents": attempts,
        "retryEvents": retries,
        "wallTimeMs": _wall_time_ms(row),
        "queueWaitMs": queue_ms,
        "autoAcceptanceRatio": acceptance,
    }


def evaluate_library(db, library_id: str, *, limit: int = 20) -> dict:
    """Only read tasks dispatched from this verified browser-space library.

    The HTTP layer supplies the already authenticated TrialStore connection.
    No user ID, database path, or owner name can be provided by the caller.
    """
    require_study_library(db, library_id)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    rows = db.execute(
        """SELECT d.task_id,d.plan_action,j.state,j.request,j.result,j.created,j.updated
           FROM study_practice_dispatches AS d
           JOIN jobs AS j ON j.id=d.task_id AND j.owner=?
           JOIN web_tasks AS t ON t.task_id=d.task_id
           WHERE t.library_id=?
           ORDER BY d.created DESC,d.task_id DESC
           LIMIT ?""",
        (OWNER, library_id, limit),
    ).fetchall()
    jobs = [_job_metrics(db, row) for row in rows]
    terminal = [job for job in jobs if job["status"] in TERMINAL]
    measured = [
        job for job in jobs
        if job["generatedCandidates"] is not None and job["generatedCandidates"] > 0
        and job["autoAcceptedCount"] is not None
        and job["autoAcceptedCount"] <= job["generatedCandidates"]
    ]
    total_candidates = sum(job["generatedCandidates"] for job in measured)
    total_accepted = sum(job["autoAcceptedCount"] for job in measured)
    elapsed = [job["wallTimeMs"] for job in terminal if job["wallTimeMs"] is not None]
    statuses = Counter(job["status"] for job in jobs)
    actions = Counter(job["planAction"] for job in jobs)
    return {
        "libraryId": library_id,
        "evaluationType": "operational_metadata_only",
        "sampleCount": len(jobs),
        "sampleLimit": limit,
        "summary": {
            "terminalCount": len(terminal),
            "succeededCount": statuses["succeeded"],
            "partialCount": statuses["partial"],
            "failedCount": statuses["failed"],
            "cancelledCount": statuses["cancelled"],
            "interruptedCount": statuses["interrupted"],
            "pendingCount": statuses["queued"] + statuses["running"],
            "completedRate": (
                round((statuses["succeeded"] + statuses["partial"]) / len(terminal), 4)
                if terminal else None
            ),
            "planActions": dict(sorted(actions.items())),
            "candidateCountMeasuredJobs": len(measured),
            "measuredGeneratedCandidates": total_candidates,
            "measuredAutoAccepted": total_accepted,
            "autoAcceptanceRatio": (
                round(total_accepted / total_candidates, 4) if total_candidates else None
            ),
            "averageTerminalWallTimeMs": (
                round(sum(elapsed) / len(elapsed)) if elapsed else None
            ),
        },
        "runs": jobs,
        "notMeasured": [
            "answerCorrectness", "citationSupportRate", "humanUsability",
            "agentDecisionQuality", "llmTokenCost",
        ],
    }
