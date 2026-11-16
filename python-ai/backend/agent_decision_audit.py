"""Privacy-safe, deterministic policy decision replay.

Only boolean predicates, bounded counts, enums and reason codes are exported.
Replay verifies policy consistency; it neither runs Skills nor verifies input
provenance or model correctness. Do not pass learner text into traces.
"""
from __future__ import annotations

from typing import Any, Mapping

BOUNDED_VERSION = "bounded-v1"
STUDY_VERSION = "study-v1"
RECOVERY_VERSION = "recovery-v1"
STUDY_STATUSES = frozenset({"ready", "needs_diagnosis", "no_weak_points"})
RECOVERY_STATES = frozenset({"queued", "running", "succeeded", "partial", "failed", "cancelled", "interrupted", "unknown"})
RECOVERY_CATEGORIES = frozenset({"unreadable_source", "visual_requires_review", "model_timeout_reported", "quality_not_verified", "unknown_failure"})


def _bounded_int(value: Any, lower: int = 0, upper: int = 100_000) -> bool:
    return type(value) is int and lower <= value <= upper


def bounded_features(state: Mapping) -> dict:
    return {
        "materialPresent": "material" in state,
        "pointsPresent": "points" in state,
        "candidatesPresent": "candidates" in state,
        "acceptedCount": len(state["accepted"]),
        "attempts": state["attempts"],
        "requestedCount": state["count"],
    }


def _minimal_bounded_state(features: dict) -> dict:
    expected = {"materialPresent", "pointsPresent", "candidatesPresent", "acceptedCount", "attempts", "requestedCount"}
    if not isinstance(features, dict) or set(features) != expected:
        raise ValueError("Invalid bounded audit predicates")
    if any(type(features[name]) is not bool for name in ("materialPresent", "pointsPresent", "candidatesPresent")):
        raise ValueError("Invalid predicate type")
    if (not _bounded_int(features["acceptedCount"], upper=12)
            or not _bounded_int(features["attempts"], upper=12)
            or not _bounded_int(features["requestedCount"], 1, 5)):
        raise ValueError("Invalid bounded audit counts")
    state = {
        "accepted": [None] * features["acceptedCount"],
        "attempts": features["attempts"],
        "count": features["requestedCount"],
    }
    if features["materialPresent"]:
        state["material"] = True
    if features["pointsPresent"]:
        state["points"] = True
    if features["candidatesPresent"]:
        state["candidates"] = True
    return state


def runtime_choice(state: Mapping, planner, step: int) -> dict:
    f = bounded_features(state)
    selected = planner.next_skill(state)
    if selected is None:
        reason = ("requested_count_reached" if f["acceptedCount"] >= f["requestedCount"]
                  else "generation_budget_exhausted")
    else:
        reason = {
            "prepare": "source_not_prepared",
            "extract": "knowledge_not_extracted",
            "review": "candidates_require_review",
            "generate": "generation_required",
        }.get(selected)
    if step > planner.max_steps and selected is not None:
        reason, selected = "step_budget_exhausted", None
    if reason is None:
        raise ValueError("Unregistered Skill decision")
    return {
        "step": step, "features": f, "selectedSkill": selected,
        "reasonCode": reason,
        "outcome": "stop" if selected is None else "pending",
        "stopReasonCode": reason if selected is None else None,
    }


def _trace_rows(trace: dict, version: str, keys: set[str]) -> list[dict]:
    if not isinstance(trace, dict) or trace.get("policyVersion") != version:
        raise ValueError("Unknown or invalid policy version")
    if set(trace) != keys:
        raise ValueError("Unexpected audit fields")
    rows = trace.get("decisions")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise ValueError("Invalid decision history")
    return rows


def _runtime_transition_valid(before: dict, after: dict, skill: str) -> bool:
    """Validate declared anonymous state transitions, not data provenance."""
    expected = dict(before)
    if skill == "prepare":
        expected["materialPresent"] = True
    elif skill == "extract":
        expected["pointsPresent"] = True
    elif skill == "generate":
        expected["candidatesPresent"] = True
        expected["attempts"] += 1
    elif skill == "review":
        if after["acceptedCount"] < before["acceptedCount"]:
            return False
        expected["candidatesPresent"] = False
        expected["acceptedCount"] = after["acceptedCount"]
    else:
        return False
    return after == expected


def _study_transition_valid(before: dict, after: dict, skill: str) -> bool:
    if skill == "get_weak_knowledge_points":
        return after["weakResultPresent"] and not after["planPresent"]
    if skill in ("plan_diagnostic", "plan_targeted", "plan_review"):
        return after == {**before, "planPresent": True}
    return False


def replay_runtime_trace(trace: dict, planner=None) -> dict:
    from .agent_runtime import BoundedPlanner
    rows = _trace_rows(trace, BOUNDED_VERSION, {"policyVersion", "budget", "decisions"})
    budget = trace.get("budget")
    if (not isinstance(budget, dict) or set(budget) != {"maxAttempts", "maxSteps"}
            or not _bounded_int(budget["maxAttempts"], 1, 3)
            or not _bounded_int(budget["maxSteps"], 3, 12)):
        raise ValueError("Invalid planner budget")
    original = BoundedPlanner(max_attempts=budget["maxAttempts"], max_steps=budget["maxSteps"])
    if planner is not None and (planner.max_attempts != original.max_attempts or planner.max_steps != original.max_steps):
        return {"matched": False, "divergentStep": 1, "reason": "policy_budget_changed"}
    active = planner or original
    ended = False
    for index, row in enumerate(rows, 1):
        if (not isinstance(row, dict) or set(row) != {
                "step", "features", "selectedSkill", "reasonCode", "outcome", "stopReasonCode"
                } or row["step"] != index or ended):
            return {"matched": False, "divergentStep": index, "reason": "malformed_sequence"}
        try:
            wanted = runtime_choice(_minimal_bounded_state(row["features"]), active, index)
        except (TypeError, ValueError, KeyError):
            return {"matched": False, "divergentStep": index, "reason": "invalid_predicates"}
        features = row["features"]
        if index == 1:
            if (features["materialPresent"] or features["candidatesPresent"]
                    or features["acceptedCount"] != 0 or features["attempts"] != 0):
                return {"matched": False, "divergentStep": index, "reason": "invalid_initial_state"}
        else:
            prior = rows[index - 2]
            if not _runtime_transition_valid(prior["features"], features, prior["selectedSkill"]):
                return {"matched": False, "divergentStep": index,
                        "reason": "inconsistent_state_transition"}
        if row["selectedSkill"] != wanted["selectedSkill"] or row["reasonCode"] != wanted["reasonCode"]:
            return {"matched": False, "divergentStep": index, "reason": "policy_choice_changed"}
        if wanted["selectedSkill"] is None:
            if row["outcome"] != "stop" or row["stopReasonCode"] != wanted["reasonCode"]:
                return {"matched": False, "divergentStep": index, "reason": "invalid_stop"}
            ended = True
        elif row["outcome"] == "failed" and row["stopReasonCode"] == "skill_execution_failed":
            ended = True
        elif row["outcome"] == "ok" and row["stopReasonCode"] is None:
            pass
        else:
            return {"matched": False, "divergentStep": index, "reason": "invalid_outcome"}
    if not ended:
        return {"matched": False, "divergentStep": len(rows), "reason": "incomplete_trace"}
    if len(rows) > active.max_steps + 1:
        return {"matched": False, "divergentStep": active.max_steps + 2, "reason": "invalid_step_budget"}
    return {"matched": True, "divergentStep": None, "reason": "policy_replayed"}


def study_features(state: Mapping) -> dict:
    weak = state.get("weak_result")
    status = weak.get("status") if isinstance(weak, dict) else None
    count = len(weak.get("weak_points", [])) if isinstance(weak, dict) else 0
    return {
        "weakResultPresent": "weak_result" in state,
        "planPresent": "plan" in state,
        "weakStatus": status if status in STUDY_STATUSES else None,
        "weakPointCount": count,
    }


def study_choice(state: Mapping, planner, step: int) -> dict:
    f = study_features(state)
    selected = planner.next_skill(state)
    reasons = {
        "get_weak_knowledge_points": "learning_evidence_needs_classification",
        "plan_diagnostic": "insufficient_learning_evidence",
        "plan_targeted": "verified_weak_points_present",
        "plan_review": "no_verified_weak_points",
        None: "study_plan_ready",
    }
    if selected not in reasons:
        raise ValueError("Unregistered study Skill decision")
    return {"step": step, "features": f, "selectedSkill": selected,
            "reasonCode": reasons[selected]}


def replay_study_trace(trace: dict, planner=None) -> dict:
    from .study_skill_planner import LearningPlanner
    rows = _trace_rows(trace, STUDY_VERSION, {"policyVersion", "decisions"})
    active = planner or LearningPlanner()
    ended = False
    for index, row in enumerate(rows, 1):
        if (not isinstance(row, dict) or set(row) != {"step", "features", "selectedSkill", "reasonCode"}
                or row["step"] != index or ended):
            return {"matched": False, "divergentStep": index, "reason": "malformed_sequence"}
        f = row["features"]
        if (not isinstance(f, dict) or set(f) != {
                "weakResultPresent", "planPresent", "weakStatus", "weakPointCount"}
                or type(f["weakResultPresent"]) is not bool
                or type(f["planPresent"]) is not bool
                or not _bounded_int(f["weakPointCount"], 0, 5)
                or (f["weakStatus"] is not None and not isinstance(f["weakStatus"], str))
                or (f["weakStatus"] is not None and f["weakStatus"] not in STUDY_STATUSES)
                or (not f["weakResultPresent"] and (f["weakStatus"] is not None or f["weakPointCount"] != 0))
                or (f["weakResultPresent"] and f["weakStatus"] is None)):
            return {"matched": False, "divergentStep": index, "reason": "invalid_predicates"}
        state = {}
        if f["weakResultPresent"]:
            state["weak_result"] = {"status": f["weakStatus"],
                                    "weak_points": [None] * f["weakPointCount"]}
        if f["planPresent"]:
            state["plan"] = {}
        if index == 1:
            if (f["weakResultPresent"] or f["planPresent"]
                    or f["weakStatus"] is not None or f["weakPointCount"] != 0):
                return {"matched": False, "divergentStep": index,
                        "reason": "invalid_initial_state"}
        else:
            prior = rows[index - 2]
            if not _study_transition_valid(prior["features"], f, prior["selectedSkill"]):
                return {"matched": False, "divergentStep": index,
                        "reason": "inconsistent_state_transition"}
        wanted = study_choice(state, active, index)
        if wanted["selectedSkill"] != row["selectedSkill"] or wanted["reasonCode"] != row["reasonCode"]:
            return {"matched": False, "divergentStep": index, "reason": "policy_choice_changed"}
        if row["selectedSkill"] is None:
            ended = True
    if not ended or len(rows) != 3:
        return {"matched": False, "divergentStep": len(rows), "reason": "incomplete_trace"}
    return {"matched": True, "divergentStep": None, "reason": "policy_replayed"}


def replay_recovery_trace(trace: dict) -> dict:
    from .agent_recovery_policy import advise_recovery, TIMEOUT_REASON
    if not isinstance(trace, dict) or trace.get("policyVersion") != RECOVERY_VERSION:
        raise ValueError("Unknown or invalid policy version")
    if set(trace) != {"policyVersion", "features", "selectedAction", "reasonCode"}:
        raise ValueError("Unexpected recovery trace fields")
    f = trace["features"]
    if (not isinstance(f, dict) or set(f) != {
            "taskStatus", "acceptedCount", "failureCategory", "existingRetry",
            "retryDepth", "sourceAvailable"}
            or not isinstance(f["taskStatus"], str)
            or f["taskStatus"] not in RECOVERY_STATES
            or (f["failureCategory"] is not None and not isinstance(f["failureCategory"], str))
            or f["failureCategory"] not in RECOVERY_CATEGORIES | {None}
            or not _bounded_int(f["acceptedCount"]) or not _bounded_int(f["retryDepth"], 0, 2)
            or type(f["existingRetry"]) is not bool
            or type(f["sourceAvailable"]) is not bool):
        return {"matched": False, "reason": "invalid_predicates"}
    markers = {
        "unreadable_source": {"status": "text_unreadable"},
        "visual_requires_review": {"status": "visual_unverified"},
        "quality_not_verified": {"status": "rejected_or_needs_review"},
        "model_timeout_reported": {"reasons": [TIMEOUT_REASON]},
    }
    result = {"accepted": f["acceptedCount"], "files": [],
              "rejected": [markers[f["failureCategory"]]] if f["failureCategory"] in markers else []}
    replayed = advise_recovery(
        {"id": "0"*32, "state": f["taskStatus"], "result": result},
        existing_retry_id="1"*32 if f["existingRetry"] else None,
        retry_depth=f["retryDepth"], source_available=f["sourceAvailable"],
    )
    if replayed["decisionTrace"] != trace:
        return {"matched": False, "reason": "policy_choice_changed"}
    return {"matched": True, "reason": "policy_replayed"}
