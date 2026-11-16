"""Conservative read-only advice for a source-grounded practice task.

This is a deterministic decision policy, NOT an autonomous retry Skill. It
does not invoke Qwen, read a user identity, write a job or trust model-provided
commands. The API layer authorizes the task and supplies scoped records.
"""
from __future__ import annotations

from typing import Any

TERMINAL = frozenset({"succeeded", "partial", "failed", "cancelled", "interrupted"})
REJECTION_STATUSES = frozenset({"text_unreadable", "visual_unverified", "rejected_or_needs_review"})
TIMEOUT_REASON = "等待本机模型响应超时，请稍后重试。"
ACTION_CODES = frozenset({
    "wait", "complete", "review_accepted", "replace_source",
    "manual_quality_review", "retry_with_confirmation", "open_existing_retry",
    "stop", "inspect_failure",
})


def _records(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _count(value: Any) -> int:
    return value if type(value) is int and value >= 0 else 0


def classify_failure(result: dict) -> str:
    """Recognize only explicit persisted markers; do not parse arbitrary text."""
    files = _records(result.get("files"))
    rejected = _records(result.get("rejected"))
    statuses = {
        entry["status"] for entry in rejected
        if isinstance(entry.get("status"), str) and entry["status"] in REJECTION_STATUSES
    }
    if "text_unreadable" in statuses or any(file.get("status") == "error" for file in files):
        return "unreadable_source"
    if "visual_unverified" in statuses:
        return "visual_requires_review"
    if any(
        TIMEOUT_REASON in item.get("reasons", [])
        for item in rejected if isinstance(item.get("reasons"), list)
    ):
        return "model_timeout_reported"
    if "rejected_or_needs_review" in statuses:
        return "quality_not_verified"
    return "unknown_failure"


def advise_recovery(
    job: dict, *,
    existing_retry_id: str | None = None,
    retry_depth: int = 0,
    source_available: bool = True,
) -> dict:
    """Provide safe UI guidance; never retry, cancel or enqueue on its own.

    `retry_depth` is measured by the trusted caller from persisted task links,
    not supplied by the browser or an LLM. One manual retry suggestion at most.
    """
    state = job.get("state")
    result = job.get("result")
    if not isinstance(result, dict):
        result = {}
    accepted = _count(result.get("accepted"))
    reason = classify_failure(result) if state in TERMINAL else None
    if state in {"queued", "running"}:
        action = "wait"
    elif state == "succeeded":
        action = "complete"
    elif state == "partial" or (state == "failed" and accepted):
        action = "review_accepted"
    elif state == "cancelled":
        action = "stop"
    elif existing_retry_id:
        action = "open_existing_retry"
    elif state not in {"failed", "interrupted"}:
        action = "inspect_failure"
    elif not source_available:
        action = "replace_source"
    elif retry_depth >= 1:
        action = "manual_quality_review"
    elif state == "interrupted":
        action = "retry_with_confirmation"
    elif reason == "unreadable_source":
        action = "replace_source"
    elif reason in {"visual_requires_review", "quality_not_verified"}:
        action = "manual_quality_review"
    elif reason == "model_timeout_reported":
        action = "retry_with_confirmation"
    else:
        action = "inspect_failure"

    if action not in ACTION_CODES:
        raise RuntimeError("Unrecognized recovery action")
    from .agent_decision_audit import RECOVERY_VERSION
    # This trace contains only anonymous, strictly typed branch predicates.
    # Never persist source content, exception strings, prompt or topic names.
    decision_trace = {
        "policyVersion": RECOVERY_VERSION,
        "features": {
            "taskStatus": state if state in TERMINAL | {"queued", "running"} else "unknown",
            "acceptedCount": accepted,
            "failureCategory": reason,
            "existingRetry": bool(existing_retry_id),
            "retryDepth": min(max(retry_depth, 0), 2),
            "sourceAvailable": bool(source_available),
        },
        "selectedAction": action,
        "reasonCode": {
            "wait": "task_in_progress",
            "complete": "task_succeeded",
            "review_accepted": "partial_results_exist",
            "stop": "user_cancelled",
            "open_existing_retry": "retry_receipt_exists",
            "replace_source": "source_unavailable_or_unreadable",
            "manual_quality_review": "human_review_required",
            "retry_with_confirmation": "recoverable_with_confirmation",
            "inspect_failure": "failure_not_classified",
        }[action],
    }
    return {
        "taskId": job["id"],
        "status": state if state in TERMINAL | {"queued", "running"} else "unknown",
        "failureCategory": reason,
        "nextAction": action,
        "requiresHumanConfirmation": action == "retry_with_confirmation",
        "willExecuteAutomatically": False,
        "remainingSuggestedRetries": max(0, 1 - max(0, retry_depth))
        if action == "retry_with_confirmation" else 0,
        "existingRetryTaskId": existing_retry_id,
        "acceptedCount": accepted,
        "note": "Automated validation does not establish factual correctness.",
        "decisionTrace": decision_trace,
    }
