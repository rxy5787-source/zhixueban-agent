"""ZH-05: privacy-preserving task stage timing derived from persisted checkpoints.

Checkpoint intervals approximate the elapsed wall time between status reports.
They are NOT isolated Qwen latency, OCR CPU time, or human-graded quality.
The returned data never includes raw stage labels, source names, prompts,
model responses, usernames, exception text, or authentication credentials.
"""
from __future__ import annotations

from collections import defaultdict
import math

TERMINAL = frozenset({"succeeded", "partial", "failed", "cancelled", "interrupted"})
_ALLOWED_PHASES = frozenset({
    "preparation", "parsing", "ocr", "knowledge", "generation", "quality",
    "checkpoint", "other",
})


def phase_from_stage(stage: str) -> str:
    if not isinstance(stage, str):
        return "other"
    if stage.startswith(("正在识别扫描文字", "正在识别图片文字", "正在识别 Word 图片文字")):
        return "ocr"
    if stage.startswith(("AI生成", "根据质检原因重新生成", "千问正在整理资料",
                         "正在编写口诀", "正在按主题整理记忆口诀")):
        return "generation"
    if stage.startswith(("自动质量初筛", "初筛通过", "正在核对原文依据",
                         "正在复核知识点覆盖与学习价值")):
        return "quality"
    if stage.startswith("正在从资料识别知识点"):
        return "knowledge"
    if stage.startswith(("解析 ", "正在复用已解析资料")):
        return "parsing"
    if stage == "准备解析":
        return "preparation"
    if stage.startswith(("已保存", "已跳过")):
        return "checkpoint"
    return "other"


def _seconds(value):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _ms(start: float, end: float) -> int:
    return max(0, round(1000 * (end - start)))


def timing_report(job: dict, events: list[dict], archive_callback_ms: int | None = None) -> dict:
    """Produce a sanitized timeline from this task's ordered event records.

    The caller has to authorize the task BEFORE passing these records. For
    preexisting jobs without an instrumented claim event, queue wait is unknown.
    """
    created = _seconds(job.get("created"))
    updated = _seconds(job.get("updated"))
    if created is None or updated is None:
        raise ValueError("Task timestamps unavailable")
    state = job["state"]
    valid = []
    last_time = created
    for event in events:
        at = _seconds(event.get("created"))
        if at is None:
            continue
        # Time may be nonmonotonic after a host clock adjustment.
        at = max(last_time, min(at, max(updated, created)))
        valid.append({"at": at, "state": event.get("state", ""),
                      "phase": phase_from_stage(event.get("stage", ""))})
        last_time = at

    queue_wait = None
    if valid and valid[0]["phase"] == "preparation" and valid[0]["state"] == "running":
        queue_wait = _ms(created, valid[0]["at"])

    accumulated = defaultdict(int)
    intervals = []
    last_active_phase = None
    for index in range(len(valid) - 1):
        previous, following = valid[index], valid[index + 1]
        if previous["state"] in TERMINAL:
            break
        phase = previous["phase"]
        if phase not in _ALLOWED_PHASES:
            phase = "other"
        duration = _ms(previous["at"], following["at"])
        accumulated[phase] += duration
        intervals.append({"phase": phase, "elapsedMs": duration})
        if phase != "other":
            last_active_phase = phase

    # Some legacy tasks have no final job_event row; their final updated
    # timestamp is a supported boundary, but a running task has no end boundary.
    if state in TERMINAL and valid and valid[-1]["state"] not in TERMINAL:
        phase = valid[-1]["phase"]
        duration = _ms(valid[-1]["at"], max(updated, valid[-1]["at"]))
        accumulated[phase] += duration
        intervals.append({"phase": phase, "elapsedMs": duration})
        if phase != "other":
            last_active_phase = phase
    elif valid and valid[-1]["state"] in TERMINAL and not intervals:
        last_active_phase = None

    archive_elapsed = (archive_callback_ms if type(archive_callback_ms) is int
                       and archive_callback_ms >= 0 else None)
    error_category = (
        "task_failed" if state == "failed" else
        "task_cancelled" if state == "cancelled" else
        "task_interrupted" if state == "interrupted" else None
    )
    return {
        "taskId": job["id"],
        "state": state,
        "timingBasis": "completed_checkpoint_intervals",
        "queueWaitMs": queue_wait,
        "phaseElapsedMs": dict(sorted(accumulated.items())),
        "phaseIntervals": intervals,
        "archiveCallbackMs": archive_elapsed,
        "terminalWallTimeMs": _ms(created, max(updated, created)) if state in TERMINAL else None,
        "errorCategory": error_category,
        "lastObservedPhase": last_active_phase,
        "limitations": [
            "checkpoint_intervals_not_exclusive_model_latency",
            "archive_callback_excludes_commit",
            "legacy_jobs_may_lack_claim_events",
        ],
    }
