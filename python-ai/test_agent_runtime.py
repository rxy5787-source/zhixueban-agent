"""Deterministic Agent/Skill tests: no live model, network or database."""
import pytest
from backend.agent_runtime import AgentRuntime, BoundedPlanner, Skill, SkillRegistry, AgentSkillError

TEXT = "WHERE 在分组前筛选原始数据行，HAVING 在分组后过滤聚合结果。WHERE 子句不能直接对聚合结果进行筛选。"

def fake_registry(fail_first=False):
    registry = SkillRegistry()
    calls = {"review": 0}
    def prepare(state): return {"material": state["source_text"]}
    def extract(state): return {"points": [{"name": "SQL", "summary": TEXT}]}
    def generate(state):
        return {"candidates": [{"question": "WHERE 的作用？"}], "attempts": state["attempts"] + 1}
    def review(state):
        calls["review"] += 1
        if fail_first and calls["review"] == 1:
            return {"accepted": [], "rejected": [{"reasons": ["evidence missing"]}], "feedback": "evidence missing"}
        return {"accepted": [{"question": "WHERE 的作用？", "answer": "A"}], "rejected": state["rejected"], "feedback": ""}
    registry.register(Skill("prepare", frozenset({"source_text"}), frozenset({"material"}), prepare))
    registry.register(Skill("extract", frozenset({"material", "goal"}), frozenset({"points"}), extract))
    registry.register(Skill("generate", frozenset({"material", "goal", "points", "accepted", "attempts", "count"}), frozenset({"attempts", "candidates"}), generate))
    registry.register(Skill("review", frozenset({"candidates", "accepted", "rejected", "material"}), frozenset({"accepted", "rejected", "feedback"}), review))
    return registry

def test_dynamic_selection():
    result = AgentRuntime(registry=fake_registry()).run(TEXT, "生成一道 WHERE 单选题", count=1)
    assert result["status"] == "succeeded"
    assert [event["skill"] for event in result["events"]] == ["prepare", "extract", "generate", "review"]
    assert result["attempts"] == 1

def test_bounded_retry():
    result = AgentRuntime(registry=fake_registry(True)).run(TEXT, "生成一道 WHERE 单选题", count=1)
    assert result["status"] == "succeeded"
    assert result["attempts"] == 2
    assert [event["skill"] for event in result["events"]] == ["prepare", "extract", "generate", "review", "generate", "review"]

def test_known_points_skip_extraction():
    result = AgentRuntime(registry=fake_registry()).run(TEXT, "生成一道 SQL 题", points=[{"name": "SQL", "summary": TEXT}], count=1)
    assert [event["skill"] for event in result["events"]] == ["prepare", "generate", "review"]

def test_registry_rejects_unregistered_and_bad_contract():
    registry = SkillRegistry()
    with pytest.raises(AgentSkillError): registry.execute("shell", {})
    registry.register(Skill("bad", frozenset({"goal"}), frozenset({"output"}), lambda _: {}))
    with pytest.raises(AgentSkillError, match="missing inputs"): registry.execute("bad", {})
    with pytest.raises(AgentSkillError, match="missing outputs"): registry.execute("bad", {"goal": "test"})

def test_budgets_and_inputs():
    runtime = AgentRuntime(registry=fake_registry(), planner=BoundedPlanner(max_steps=3))
    result = runtime.run(TEXT, "生成一道 SQL 题")
    assert result["error"] == "step_budget_exceeded"
    with pytest.raises(ValueError): runtime.run(TEXT, " ")
    with pytest.raises(ValueError): runtime.run(TEXT, "生成题目", count=100)

def test_failures_do_not_expose_source_in_events():
    broken = SkillRegistry()
    def explode(state): raise ValueError("sensitive sentence: " + state["source_text"])
    broken.register(Skill("prepare", frozenset({"source_text"}), frozenset({"material"}), explode))
    result = AgentRuntime(registry=broken).run(TEXT, "生成题目", count=1)
    assert result["status"] == "failed"
    assert TEXT not in str(result["events"])
    assert TEXT not in result["error"]

def test_zh06_eval_contract_and_unmeasured_quality():
    """CI smoke test of the quality harness; no model or network involved."""
    from evaluation.zh06 import build_report, case_prompt, load_cases

    cases = load_cases()
    assert [case["id"] for case in cases] == list(range(1, 21))
    assert sum(case["negative"] for case in cases) == 1
    assert "拒绝" not in case_prompt(cases[-1])  # Never give the model the expected verdict.
    empty = build_report({}, {})
    assert empty["humanUsability"]["rate"] is None
    assert empty["factualCorrectness"]["denominator"] == 0
    assert empty["medianTaskWallMs"] is None
