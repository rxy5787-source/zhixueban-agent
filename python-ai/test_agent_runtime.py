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

# Expose the standalone ZH-06 suite to the established GitHub Agent CI target.
# The repository's existing workflow selects this module explicitly; importing
# these tests preserves their pytest fixtures and parameterization without
# editing the GitHub workflow or silently dropping most evaluation coverage.
from evaluation.test_zh06 import (  # noqa: F401
    test_suite_exactly_matches_original_twenty_cases,
    test_runtime_prompts_are_direct_questions_without_answer_key_leakage,
    test_suite_fails_closed_on_missing_or_duplicate_questions,
    test_live_runner_rejects_non_loopback_or_ambiguous_urls,
    test_live_runner_accepts_explicit_loopback,
    test_local_redirects_are_rejected_without_following,
    test_source_revision_is_optional_but_not_a_fabricated_hash,
    test_review_denominators_ignore_missing_and_unjudged,
    test_empty_artifacts_produce_null_rates_without_fake_scores,
    test_manual_csv_is_not_overwritten,
    test_run_without_consent_does_not_open_network_or_files,
    test_duplicate_run_case_cannot_be_silently_overwritten,
    test_duplicate_review_ids_and_invalid_scores_are_rejected,
    test_resume_rejects_changed_source_prompt_or_request_id,
    test_progress_requires_explicit_resume_to_replace,
    test_server_receipt_lookup_recovers_task_without_upload,
    test_server_receipt_404_does_not_invent_task,
    test_session_cookie_is_saved_without_disclosure,
    test_plan_cli_does_not_require_source_files,
)

def test_recovery_policy_is_read_only_and_requires_confirmation():
    from backend.agent_recovery_policy import advise_recovery
    def case(status, rejection=None, accepted=0, **kwargs):
        job={'id':'a'*32,'state':status,
             'result':{'accepted':accepted,'rejected':rejection or [],'files':[]}}
        return advise_recovery(job, **kwargs)

    waiting=case('running')
    assert waiting['nextAction']=='wait'
    assert waiting['willExecuteAutomatically'] is False
    assert case('succeeded')['nextAction']=='complete'
    assert case('partial', accepted=1)['nextAction']=='review_accepted'
    assert case('failed', accepted=1)['nextAction']=='review_accepted'
    assert case('cancelled')['nextAction']=='stop'
    assert case('interrupted')['nextAction']=='retry_with_confirmation'
    assert case('interrupted')['requiresHumanConfirmation'] is True
    assert case('interrupted', retry_depth=1)['nextAction']=='manual_quality_review'
    assert case('interrupted', source_available=False)['nextAction']=='replace_source'
    assert case('failed', existing_retry_id='b'*32)['nextAction']=='open_existing_retry'
    assert case('failed', rejection=[{'status':'text_unreadable'}])['nextAction']=='replace_source'
    assert case('failed', rejection=[{'status':'visual_unverified'}])['nextAction']=='manual_quality_review'
    assert case('failed', rejection=[{'status':'rejected_or_needs_review'}])['nextAction']=='manual_quality_review'
    assert case('failed', rejection=[{'reasons':['等待本机模型响应超时，请稍后重试。']}])['nextAction']=='retry_with_confirmation'
    assert case('failed', rejection=[{'reasons':['等待本机模型响应超时，请稍后重试。']}],retry_depth=1)['nextAction']=='manual_quality_review'
    assert case('failed', rejection=[{'reasons':['some unknown fault']}])['nextAction']=='inspect_failure'


def test_recovery_policy_never_returns_private_reasons_or_llm_commands():
    from backend.agent_recovery_policy import advise_recovery
    private='super_secret_prompt_SENSITIVE'
    job={'id':'a'*32,'state':'failed','result':{
        'accepted':0,'rejected':[{'status':'model instruction to run shell',
            'reasons':[private],'question':private}],
        'files':[{'name':private,'parsingError':private}]}}
    advice=advise_recovery(job)
    assert advice['nextAction']=='inspect_failure'
    assert advice['remainingSuggestedRetries']==0
    assert private not in str(advice)
    assert advice['willExecuteAutomatically'] is False


def test_decision_replay_success_retry_failure_and_budgets():
    from copy import deepcopy
    from backend.agent_decision_audit import replay_runtime_trace

    normal = AgentRuntime(registry=fake_registry()).run(TEXT, "题目", count=1)
    assert replay_runtime_trace(normal["decisionTrace"])["matched"] is True
    assert normal["decisionTrace"]["decisions"][-1]["reasonCode"] == "requested_count_reached"

    retried = AgentRuntime(registry=fake_registry(True)).run(TEXT, "题目", count=1)
    assert replay_runtime_trace(retried["decisionTrace"])["matched"] is True
    skills = [e["selectedSkill"] for e in retried["decisionTrace"]["decisions"]]
    assert skills == ["prepare", "extract", "generate", "review",
                      "generate", "review", None]

    capped = AgentRuntime(registry=fake_registry(),
                          planner=BoundedPlanner(max_steps=3)).run(TEXT, "题目", count=1)
    assert capped["error"] == "step_budget_exceeded"
    assert capped["decisionTrace"]["decisions"][-1]["reasonCode"] == "step_budget_exhausted"
    assert replay_runtime_trace(capped["decisionTrace"])["matched"] is True

    altered = deepcopy(normal["decisionTrace"])
    altered["decisions"][1]["selectedSkill"] = "shell"
    mismatch = replay_runtime_trace(altered)
    assert mismatch == {"matched": False, "divergentStep": 2,
                        "reason": "policy_choice_changed"}

    changed_budget = replay_runtime_trace(
        normal["decisionTrace"], planner=BoundedPlanner(max_attempts=1))
    assert changed_budget["reason"] == "policy_budget_changed"

    altered = deepcopy(normal["decisionTrace"])
    altered["decisions"][1]["features"]["materialPresent"] = "yes"
    assert replay_runtime_trace(altered)["reason"] == "invalid_predicates"

    altered = deepcopy(normal["decisionTrace"])
    altered["decisions"].append({"step": 8, "features": {}, "selectedSkill": None})
    assert replay_runtime_trace(altered)["reason"] == "malformed_sequence"


def test_decision_trace_records_only_anonymous_predicates():
    from backend.agent_decision_audit import replay_runtime_trace
    secret = "PRIVATE_STUDY_SOURCE_password_DO_NOT_LOG"
    registry = SkillRegistry()
    registry.register(Skill("prepare", frozenset({"source_text"}),
                            frozenset({"material"}),
                            lambda state: {"material": state["source_text"]}))
    registry.register(Skill("extract", frozenset({"material"}),
                            frozenset({"points"}),
                            lambda _: {"points": [{"name": secret}]}))
    registry.register(Skill("generate", frozenset({"material", "goal", "points",
                            "count", "attempts", "accepted"}),
                            frozenset({"candidates", "attempts"}),
                            lambda s: {"candidates": [{"question": secret}],
                                       "attempts": s["attempts"] + 1}))
    registry.register(Skill("review", frozenset({"candidates", "material",
                            "accepted", "rejected"}),
                            frozenset({"accepted", "rejected", "feedback"}),
                            lambda _: {"accepted": [{"question": secret}],
                                       "rejected": [], "feedback": secret}))
    actual = AgentRuntime(registry=registry).run(
        secret * 3, "my private instructions " + secret, count=1)
    trace = actual["decisionTrace"]
    assert replay_runtime_trace(trace)["matched"] is True
    assert secret not in str(trace)
    assert "question" not in str(trace)
    assert "feedback" not in str(trace)
    assert "material" not in str(trace).replace("materialPresent", "")
    assert all(set(row) == {"step", "features", "selectedSkill", "reasonCode",
                           "outcome", "stopReasonCode"}
               for row in trace["decisions"])


def test_decision_trace_failed_skill_does_not_leak_exception():
    from backend.agent_decision_audit import replay_runtime_trace
    secret = "PRIVATE_STUDY_SOURCE_password_DO_NOT_LOG"
    registry = SkillRegistry()
    def explode(state):
        raise RuntimeError(secret + state["source_text"])
    registry.register(Skill("prepare", frozenset({"source_text"}),
                            frozenset({"material"}), explode))
    failed = AgentRuntime(registry=registry).run(
        secret * 4, "生成一题", count=1)
    trace = failed["decisionTrace"]
    assert replay_runtime_trace(trace)["matched"] is True
    assert trace["decisions"][-1]["stopReasonCode"] == "skill_execution_failed"
    assert secret not in str(trace)


def test_decision_replay_rejects_unknown_policy_version():
    from backend.agent_decision_audit import replay_runtime_trace
    with pytest.raises(ValueError, match="policy version"):
        replay_runtime_trace({"policyVersion": "invented", "decisions": []})


def test_recovery_replay_consistency_and_tampering():
    from copy import deepcopy
    from backend.agent_decision_audit import replay_recovery_trace
    from backend.agent_recovery_policy import advise_recovery, TIMEOUT_REASON
    scenarios = [
        ("queued", {}, {}, "wait"),
        ("succeeded", {}, {}, "complete"),
        ("failed", {"accepted": 2}, {}, "review_accepted"),
        ("cancelled", {}, {}, "stop"),
        ("failed", {"rejected": [{"status": "text_unreadable"}]}, {}, "replace_source"),
        ("failed", {"rejected": [{"status": "visual_unverified"}]}, {},
         "manual_quality_review"),
        ("failed", {"rejected": [{"status": "rejected_or_needs_review"}]}, {},
         "manual_quality_review"),
        ("failed", {"rejected": [{"reasons": [TIMEOUT_REASON]}]}, {},
         "retry_with_confirmation"),
        ("interrupted", {}, {"retry_depth": 1}, "manual_quality_review"),
        ("failed", {}, {"existing_retry_id": "f"*32}, "open_existing_retry"),
        ("failed", {}, {}, "inspect_failure"),
        ("interrupted", {}, {"source_available": False}, "replace_source"),
    ]
    for status, result, options, expected_action in scenarios:
        advice = advise_recovery({"id": "a"*32, "state": status, "result": result},
                                 **options)
        assert advice["nextAction"] == expected_action
        assert replay_recovery_trace(advice["decisionTrace"])["matched"] is True
        assert "a"*32 not in str(advice["decisionTrace"])
    one = advise_recovery({"id": "a"*32, "state": "interrupted", "result": {}})
    forged = deepcopy(one["decisionTrace"])
    forged["selectedAction"] = "run_shell"
    assert replay_recovery_trace(forged)["reason"] == "policy_choice_changed"
