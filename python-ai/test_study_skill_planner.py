"""Exercise the real registry and planner with synthetic learning evidence."""
import pytest

from backend.agent_runtime import AgentSkillError
from backend.study_skill_planner import (
    LearningPlanner, plan_study_from_progress, study_registry,
)


def point(name, count, correct, mastery):
    return {
        "point": name,
        "observations": count,
        "correct": correct,
        "mastery": mastery,
    }


def test_no_history_plans_diagnosis():
    result = plan_study_from_progress([])
    assert result.status == "needs_diagnosis"
    assert result.next_action == "prepare_diagnostic"
    assert result.visited_skills == [
        "get_weak_knowledge_points", "plan_diagnostic",
    ]


def test_single_wrong_answer_does_not_claim_weakness():
    result = plan_study_from_progress([point("HAVING", 1, 0, .20)])
    assert result.next_action == "prepare_diagnostic"
    assert result.topics == []
    assert result.reason == "insufficient_observations"


def test_evidence_backed_weakness_plans_targeted_practice():
    result = plan_study_from_progress([
        point("WHERE", 8, 7, .9),
        point("GROUP BY", 5, 2, .35),
        point("HAVING", 4, 1, .28),
    ])
    assert result.status == "ready"
    assert result.next_action == "prepare_targeted_practice"
    assert result.topics == ["HAVING", "GROUP BY"]
    assert result.visited_skills[-1] == "plan_targeted"


def test_no_weakness_plans_general_review():
    result = plan_study_from_progress([point("WHERE", 5, 5, .8)])
    assert result.status == "no_weak_points"
    assert result.next_action == "prepare_review"
    assert result.visited_skills[-1] == "plan_review"


def test_invalid_records_do_not_trigger_fallback_guessing():
    with pytest.raises(ValueError):
        plan_study_from_progress([point("WHERE", 3, 5, .8)])


def test_registry_refuses_unknown_actions_and_missing_fields():
    registry = study_registry()
    with pytest.raises(AgentSkillError, match="Unregistered"):
        registry.execute("shell", {"progress": []})
    with pytest.raises(AgentSkillError, match="missing inputs"):
        registry.execute("get_weak_knowledge_points", {})


def test_untrusted_or_malformed_status_is_rejected():
    with pytest.raises(AgentSkillError, match="Unexpected"):
        LearningPlanner().next_skill({"weak_result": {"status": "invented"}})
    with pytest.raises(ValueError):
        plan_study_from_progress({"points": []})


def test_study_decision_trace_replays_all_three_branches():
    from backend.agent_decision_audit import replay_study_trace
    scenarios = [
        ([], "plan_diagnostic", "insufficient_learning_evidence"),
        ([point("HAVING", 5, 2, .3)], "plan_targeted", "verified_weak_points_present"),
        ([point("WHERE", 5, 5, .9)], "plan_review", "no_verified_weak_points"),
    ]
    for progress, skill, reason in scenarios:
        plan = plan_study_from_progress(progress)
        trace = plan.decision_trace
        assert [d["selectedSkill"] for d in trace["decisions"]] == [
            "get_weak_knowledge_points", skill, None,
        ]
        assert trace["decisions"][1]["reasonCode"] == reason
        assert replay_study_trace(trace) == {
            "matched": True, "divergentStep": None, "reason": "policy_replayed",
        }
        assert "HAVING" not in str(trace)
        assert "WHERE" not in str(trace)


def test_study_replay_detects_forged_choices_and_evidence():
    from copy import deepcopy
    from backend.agent_decision_audit import replay_study_trace
    trace = plan_study_from_progress([point("HAVING", 5, 2, .2)]).decision_trace
    altered = deepcopy(trace)
    altered["decisions"][1]["selectedSkill"] = "plan_review"
    assert replay_study_trace(altered)["reason"] == "policy_choice_changed"
    altered = deepcopy(trace)
    altered["decisions"][1]["features"]["weakStatus"] = "unknown"
    assert replay_study_trace(altered)["reason"] == "invalid_predicates"
    altered = deepcopy(trace)
    altered["decisions"].pop()
    assert replay_study_trace(altered)["reason"] == "incomplete_trace"
