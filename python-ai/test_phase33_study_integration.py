"""Phase 33: enforce consistent BKT classification -> allowlisted study plan.

Uses deterministic synthetic progress only. No user records, Qwen or writes.
"""
import pytest

from backend.agent_runtime import AgentSkillError
from backend.study_skill_planner import plan_study_from_progress, study_registry
from backend.weak_points_skill import get_weak_knowledge_points


def progress(name, count, correct, mastery):
    return {"point": name, "observations": count, "correct": correct, "mastery": mastery}


@pytest.mark.parametrize("rows,expected_action", [
    ([], "prepare_diagnostic"),
    ([progress("HAVING", 1, 0, 0.1)], "prepare_diagnostic"),
    ([progress("HAVING", 5, 1, 0.2)], "prepare_targeted_practice"),
    ([progress("WHERE", 5, 4, 0.8)], "prepare_review"),
])
def test_study_plan_preserves_weak_point_skill_verdict(rows, expected_action):
    classification = get_weak_knowledge_points(rows)
    plan = plan_study_from_progress(rows)
    assert plan.status == classification.status
    assert plan.next_action == expected_action
    assert plan.visited_skills == [
        "get_weak_knowledge_points",
        {"needs_diagnosis": "plan_diagnostic", "ready": "plan_targeted",
         "no_weak_points": "plan_review"}[classification.status],
    ]
    assert plan.topics == [
        item.knowledge_point for item in classification.weak_points
    ]


def test_study_planner_rejects_invalid_evidence_and_non_allowlisted_execution():
    with pytest.raises(ValueError):
        plan_study_from_progress([progress("HAVING", 2, 3, .2)])
    registry = study_registry()
    assert set(registry.names) == {
        "get_weak_knowledge_points", "plan_diagnostic", "plan_targeted", "plan_review"
    }
    with pytest.raises(AgentSkillError):
        registry.execute("shell", {"progress": []})
