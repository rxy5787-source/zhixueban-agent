"""Bounded, auditable skill dispatcher for local text-to-practice Agent experiments.

This module does not replace the production Worker or allow arbitrary tool execution.
Only explicitly registered skills can run. No source text or model response is logged.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Mapping


class AgentSkillError(RuntimeError):
    """A declared skill could not safely execute."""


@dataclass(frozen=True)
class Skill:
    name: str
    requires: frozenset[str]
    provides: frozenset[str]
    handler: Callable[[dict], Mapping]


class SkillRegistry:
    """Allowlist of callable skills with explicit input/output contracts."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Duplicate skill: {skill.name}")
        self._skills[skill.name] = skill

    def execute(self, name: str, state: dict) -> dict:
        if name not in self._skills:
            raise AgentSkillError(f"Unregistered skill: {name}")
        spec = self._skills[name]
        missing = spec.requires - state.keys()
        if missing:
            raise AgentSkillError(f"{name} missing inputs: {', '.join(sorted(missing))}")
        result = spec.handler(state)
        if not isinstance(result, Mapping):
            raise AgentSkillError(f"{name} must return a mapping")
        missing_output = spec.provides - result.keys()
        if missing_output:
            raise AgentSkillError(f"{name} missing outputs: {', '.join(sorted(missing_output))}")
        return dict(result)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._skills)


class BoundedPlanner:
    """Re-plan after each result using task state, never a model-generated tool name.

    The current pilot handles a single intent (source-grounded practice questions).
    It skips extraction when points already exist, and may retry generation after
    review feedback. Explicit budgets prevent unbounded loops.
    """

    def __init__(self, max_attempts: int = 2, max_steps: int = 8):
        if not 1 <= max_attempts <= 3 or not 3 <= max_steps <= 12:
            raise ValueError("Planner budgets out of supported range")
        self.max_attempts = max_attempts
        self.max_steps = max_steps

    def next_skill(self, state: dict) -> str | None:
        if "material" not in state:
            return "prepare"
        if "points" not in state:
            return "extract"
        if "candidates" in state:
            return "review"
        if len(state["accepted"]) >= state["count"] or state["attempts"] >= self.max_attempts:
            return None
        return "generate"


def default_registry() -> SkillRegistry:
    """Adapters reuse the existing Qwen generator and independent review modules.

    Model calls are made only when the caller explicitly runs this pilot.
    """

    def prepare(state):
        material = state["source_text"].strip()
        if not 40 <= len(material) <= 5000:
            raise AgentSkillError("Provide 40–5000 characters of extracted source text")
        return {"material": material}

    def extract(state):
        from .knowledge_extractor import derive_points
        points = derive_points(state["material"], state["goal"], lambda *_: None)
        return {"points": points}

    def generate(state):
        import generate_from_file as generator
        from . import config

        generator.OLLAMA_URL = config.OLLAMA_URL
        generator.MODEL_NAME = config.TEXT_MODEL
        remaining = min(4, state["count"] - len(state["accepted"]))
        candidates = generator.generate_questions(
            state["material"],
            question_count=remaining,
            knowledge_points=state["points"],
            timeout=min(config.MODEL_TIMEOUT, 180),
            raw_candidates=True,
            feedback=state.get("feedback"),
            requirements=state["goal"],
            used_evidence=[q.get("evidenceQuote", "") for q in state["accepted"]],
            allow_rule_generation=False,
            compact_source=True,
        )
        return {"candidates": candidates or [], "attempts": state["attempts"] + 1}

    def review(state):
        import automatic_question_validator as validator
        from . import config, web_question_review

        validator.OLLAMA_URL = config.OLLAMA_URL
        validator.REVIEW_MODEL = config.TEXT_MODEL
        validator.REVIEW_TIMEOUT = min(config.MODEL_TIMEOUT, 180)
        candidates = state["candidates"]
        if candidates:
            passed, rejected = web_question_review.validate_questions(
                candidates, state["material"], state["accepted"]
            )
        else:
            passed, rejected = [], [{"reasons": ["No candidates generated"]}]
        reasons = [
            str(reason)[:140]
            for entry in rejected[-3:]
            for reason in entry.get("reasons", [])[:2]
        ]
        return {
            "accepted": (state["accepted"] + passed)[: state["count"]],
            "rejected": state["rejected"] + rejected,
            "feedback": "；".join(reasons)[:600],
        }

    registry = SkillRegistry()
    registry.register(Skill("prepare", frozenset({"source_text"}), frozenset({"material"}), prepare))
    registry.register(Skill("extract", frozenset({"material", "goal"}), frozenset({"points"}), extract))
    registry.register(Skill("generate", frozenset({"material", "goal", "points", "count", "attempts", "accepted"}),
                            frozenset({"candidates", "attempts"}), generate))
    registry.register(Skill("review", frozenset({"candidates", "material", "accepted", "rejected"}),
                            frozenset({"accepted", "rejected", "feedback"}), review))
    return registry


class AgentRuntime:
    """Opt-in, in-process execution; never writes to the production database."""

    def __init__(self, registry: SkillRegistry | None = None, planner: BoundedPlanner | None = None):
        self.registry = registry if registry is not None else default_registry()
        self.planner = planner if planner is not None else BoundedPlanner()

    def run(self, source_text: str, goal: str, count: int = 3,
            points: list[dict] | None = None) -> dict:
        if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 500:
            raise ValueError("Goal must be 1–500 characters")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 5:
            raise ValueError("Question count must be 1–5")
        state: dict = {
            "source_text": source_text, "goal": goal.strip(), "count": count,
            "accepted": [], "rejected": [], "attempts": 0,
        }
        if points is not None:
            if not isinstance(points, list) or len(points) > 12:
                raise ValueError("Provide up to 12 knowledge points")
            state["points"] = points

        from .agent_decision_audit import BOUNDED_VERSION, runtime_choice
        events: list[dict] = []
        decisions: list[dict] = []
        failure = ""
        for step in range(self.planner.max_steps):
            decision = runtime_choice(state, self.planner, step + 1)
            decisions.append(decision)
            name = decision["selectedSkill"]
            if name is None:
                break
            start = time.monotonic()
            try:
                result = self.registry.execute(name, state)
                state.update(result)
                if name == "review":
                    state.pop("candidates", None)
                decision["outcome"] = "ok"
                events.append({"step": step + 1, "skill": name, "status": "ok",
                               "durationMs": round((time.monotonic() - start) * 1000)})
            except Exception as exc:
                # Keep exception text, source, goal, candidate payload and
                # generated feedback out of the decision audit.
                failure = f"{name}: {type(exc).__name__}"
                decision["outcome"] = "failed"
                decision["stopReasonCode"] = "skill_execution_failed"
                events.append({"step": step + 1, "skill": name, "status": "failed",
                               "errorType": type(exc).__name__})
                break
        else:
            decision = runtime_choice(state, self.planner, self.planner.max_steps + 1)
            decisions.append(decision)
            if decision["reasonCode"] == "step_budget_exhausted":
                failure = "step_budget_exceeded"

        accepted = state["accepted"]
        status = "failed" if failure else ("succeeded" if len(accepted) == count
                                           else "partial" if accepted else "failed")
        return {
            "status": status, "accepted": accepted, "rejected": state["rejected"],
            "events": events, "attempts": state["attempts"],
            "requestedCount": count, "acceptedCount": len(accepted),
            "error": failure or ("" if accepted else "No validated questions"),
            "decisionTrace": {
                "policyVersion": BOUNDED_VERSION,
                "budget": {"maxAttempts": self.planner.max_attempts,
                           "maxSteps": self.planner.max_steps},
                "decisions": decisions,
            },
        }
