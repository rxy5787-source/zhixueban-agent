"""Opt-in learning-task planner demonstrating SkillRegistry + BKT evidence routing.

This is a *planning* runtime: it returns the proposed next action, never
generates questions, accesses user records, or writes to a database.
The caller must supply progress retrieved from an authorized library.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, Field

from .agent_runtime import AgentSkillError, Skill, SkillRegistry
from .weak_points_skill import get_weak_knowledge_points


class StudyPlan(BaseModel):
    status: Literal["needs_diagnosis", "ready", "no_weak_points"]
    next_action: Literal["prepare_diagnostic", "prepare_targeted_practice", "prepare_review"]
    topics: list[str] = Field(default_factory=list)
    reason: str
    visited_skills: list[str]
    decision_trace: dict = Field(default_factory=dict)


class LearningPlanner:
    """Select a registered next skill based on validated learning evidence."""

    def next_skill(self, state: Mapping) -> str | None:
        if "weak_result" not in state:
            return "get_weak_knowledge_points"
        if "plan" in state:
            return None
        status = state["weak_result"]["status"]
        if status == "needs_diagnosis":
            return "plan_diagnostic"
        if status == "ready":
            return "plan_targeted"
        if status == "no_weak_points":
            return "plan_review"
        raise AgentSkillError("Unexpected weak-point status")


def study_registry() -> SkillRegistry:
    """All skills are allowlisted; no model-supplied function names are executed."""
    registry = SkillRegistry()

    def assess(state: dict) -> dict:
        result = get_weak_knowledge_points(state["progress"])
        return {"weak_result": result.model_dump()}

    def diagnostic(state: dict) -> dict:
        return {"plan": {
            "status": "needs_diagnosis",
            "next_action": "prepare_diagnostic",
            "topics": [],
            "reason": state["weak_result"]["reason"],
        }}

    def targeted(state: dict) -> dict:
        weak = state["weak_result"]["weak_points"]
        return {"plan": {
            "status": "ready",
            "next_action": "prepare_targeted_practice",
            "topics": [item["knowledge_point"] for item in weak],
            "reason": state["weak_result"]["reason"],
        }}

    def review(state: dict) -> dict:
        return {"plan": {
            "status": "no_weak_points",
            "next_action": "prepare_review",
            "topics": [],
            "reason": state["weak_result"]["reason"],
        }}

    registry.register(Skill(
        "get_weak_knowledge_points",
        frozenset({"progress"}), frozenset({"weak_result"}), assess,
    ))
    for name, handler in (
        ("plan_diagnostic", diagnostic),
        ("plan_targeted", targeted),
        ("plan_review", review),
    ):
        registry.register(Skill(
            name, frozenset({"weak_result"}), frozenset({"plan"}), handler,
        ))
    return registry


def plan_study_from_progress(
    progress: list[dict], *,
    registry: SkillRegistry | None = None,
    planner: LearningPlanner | None = None,
) -> StudyPlan:
    """Build a deterministic, read-only learning plan (not execute it).

    `progress` MUST come from a trusted, owner-scoped lookup. Do not pass
    untrusted model-produced progress or use an LLM-provided library ID.
    """
    if not isinstance(progress, list):
        raise ValueError("progress must be an authorized progress list")

    state = {"progress": progress}
    registry = registry if registry is not None else study_registry()
    planner = planner if planner is not None else LearningPlanner()
    from .agent_decision_audit import STUDY_VERSION, study_choice
    visited: list[str] = []
    decisions: list[dict] = []

    # Two Skill transitions plus a terminal STOP; no model calls here.
    for step in range(1, 4):
        decision = study_choice(state, planner, step)
        decisions.append(decision)
        name = decision["selectedSkill"]
        if name is None:
            if "plan" not in state:
                raise AgentSkillError("Planner stopped without producing a plan")
            return StudyPlan(
                **state["plan"], visited_skills=visited,
                decision_trace={"policyVersion": STUDY_VERSION, "decisions": decisions},
            )
        state.update(registry.execute(name, state))
        visited.append(name)
    raise AgentSkillError("Learning planner exceeded step budget")
