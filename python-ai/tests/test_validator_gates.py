"""Decision logic of the question validator.

Model calls are replaced by fakes, so these tests check which gate rejects a
candidate and whether the (slow) model review is skipped when an earlier gate
already failed. Real model quality is a separate evaluation.
"""

import copy

import pytest
import requests

import automatic_question_validator as v

SOURCE = "WHERE 在分组之前过滤原始数据行。HAVING 在分组之后过滤聚合结果。"
EXPLANATION = "WHERE 在分组之前过滤原始数据行。"

GOOD = {
    "question": "按部门分组之前，先排除不满足条件的原始记录，应使用哪个子句？",
    "options": {"A": "WHERE", "B": "HAVING", "C": "GROUP BY", "D": "ORDER BY"},
    "answer": "A",
    "explanation": EXPLANATION,
    "knowledgePoint": "WHERE 过滤",
    "difficulty": "简单",
}


def variant(**changes):
    q = copy.deepcopy(GOOD)
    q.update(changes)
    return q


# --------------------------------------------------------------------------
# Structural gate
# --------------------------------------------------------------------------


def test_well_formed_question_has_no_structural_errors():
    assert v.check_structure(GOOD) == []


@pytest.mark.parametrize(
    "candidate, expected",
    [
        ("not a dict", "题目不是JSON对象"),
        (variant(question="太短"), "题干为空或过短"),
        (
            variant(options={"A": "WHERE", "B": "HAVING", "C": "GROUP BY"}),
            "选项必须恰好包含A/B/C/D",
        ),
        (
            variant(options={"A": "WHERE", "B": "where", "C": "GROUP BY", "D": "ORDER BY"}),
            "存在内容相同的选项",
        ),
        (
            variant(options={"A": "5分钟", "B": "五分钟", "C": "6分钟", "D": "7分钟"}),
            "存在数值与单位含义相同的选项",
        ),
        (variant(answer="E"), "标准答案必须是A/B/C/D之一"),
        (variant(explanation=""), "缺少explanation"),
        (variant(difficulty="极难"), "难度必须是简单/中等/困难"),
        (variant(difficultyError=True), "题目难度不符合本次要求"),
        (variant(mappingError=True), "知识点不在本次规范目录中"),
        (variant(question=EXPLANATION), "题干直接复制了解析并泄露答案，不能作为独立练习题"),
        (
            variant(question="如图所示，应使用哪个子句过滤行？"),
            "题目依赖缺失的图形或上下文，不能独立作答",
        ),
        (variant(question="第3题的正确答案是？"), "题干只引用原资料的题号，缺少可独立作答的题意"),
        (
            variant(question="哪一句原文说明了分组前过滤？"),
            "题目考查内部原文编号，不能作为独立的知识题",
        ),
    ],
)
def test_structure_gate_names_the_failed_rule(candidate, expected):
    assert expected in v.check_structure(candidate)


# --------------------------------------------------------------------------
# Near-duplicate gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "new, old, expected",
    [
        (
            "按部门分组之前先排除原始记录应使用哪个子句",
            "按部门分组之前先排除原始记录应使用哪个子句",
            True,
        ),
        (
            "按部门分组之前先排除原始记录应使用哪个子句？",
            "按部门分组之前先排除原始记录应使用哪个子句吗",
            True,
        ),
        (
            "按部门分组之前先排除原始记录应使用哪个子句",
            "聚合结果过滤应当放在分组之后的哪个子句",
            False,
        ),
        # Very short stems are only duplicates when they are identical.
        ("WHERE的作用", "WHERE的功能", False),
        ("WHERE的作用", "WHERE的作用", True),
    ],
)
def test_near_duplicate_detection(new, old, expected):
    assert v.find_near_duplicate(new, [{"question": old}]) is expected


# --------------------------------------------------------------------------
# Full gate order with fake reviewers
# --------------------------------------------------------------------------


class Reviewers:
    """Replace the two model calls and count how often they are used."""

    def __init__(self, monkeypatch, **review):
        self.calls = {"answer": 0, "explanation": 0}
        review_fields = dict(
            selectedAnswers=["A"],
            answerableFromSource=True,
            ambiguous=False,
            evidenceQuote=EXPLANATION,
            requiresVisual=False,
        )
        review_fields.update(review.pop("answer", {}))
        explanation_fields = dict(consistent=True, supportedBySource=True, issues=[])
        explanation_fields.update(review.pop("explanation", {}))
        self.failure = review.pop("failure", None)

        def fake_answer(q, source_text):
            self.calls["answer"] += 1
            if self.failure:
                raise self.failure
            return v.IndependentReview(**review_fields)

        def fake_explanation(q, source_text):
            self.calls["explanation"] += 1
            return v.ExplanationReview(**explanation_fields)

        monkeypatch.setattr(v, "independent_review", fake_answer)
        monkeypatch.setattr(v, "review_explanation", fake_explanation)


def run(question, *, previous=None, source=SOURCE):
    return v.validate_questions([question], source, previous)


def reasons(rejected):
    return [reason for row in rejected for reason in row["reasons"]]


def test_consistent_candidate_is_prechecked(monkeypatch):
    fake = Reviewers(monkeypatch)
    passed, rejected = run(GOOD)
    assert rejected == []
    assert len(passed) == 1
    assert passed[0]["reviewStatus"] == "auto_prechecked"
    assert passed[0]["evidenceQuote"] == EXPLANATION
    assert fake.calls == {"answer": 1, "explanation": 1}


@pytest.mark.parametrize(
    "answer, expected",
    [
        ({"selectedAnswers": ["B"]}, "独立解答与生成答案不一致"),
        ({"selectedAnswers": ["A", "B"], "ambiguous": True}, "模型认为答案不唯一或存在歧义"),
        ({"selectedAnswers": [], "answerableFromSource": False}, "模型认为原文无法直接确定答案"),
        ({"requiresVisual": True}, "题目需要查看原图或图表，文字证据不足，不能自动导入"),
        ({"evidenceQuote": "原文里没有这句话"}, "缺少能够在原文中定位的有效逐字证据"),
        ({"evidenceQuote": ""}, "缺少能够在原文中定位的有效逐字证据"),
    ],
)
def test_independent_answer_gate(monkeypatch, answer, expected):
    Reviewers(monkeypatch, answer=answer)
    passed, rejected = run(GOOD)
    assert passed == []
    assert expected in reasons(rejected)


def test_explanation_review_can_reject(monkeypatch):
    Reviewers(monkeypatch, explanation={"consistent": False, "issues": ["引入了原文没有的断言"]})
    passed, rejected = run(GOOD)
    assert passed == []
    assert any("解析存在不一致或缺乏原文依据" in r for r in reasons(rejected))


def test_model_failure_rejects_instead_of_passing(monkeypatch):
    Reviewers(monkeypatch, failure=requests.ConnectionError("ollama is down"))
    passed, rejected = run(GOOD)
    assert passed == []
    assert any(r.startswith("AI核验失败") for r in reasons(rejected))


@pytest.mark.parametrize(
    "candidate, previous, source, expected",
    [
        # Structural failure.
        (variant(answer="E"), None, SOURCE, "标准答案必须是A/B/C/D之一"),
        # Explanation must be a verbatim excerpt of the source.
        (variant(explanation="WHERE 会在分组前先筛掉不需要的数据"), None, SOURCE, "逐字原文摘录"),
        # Too close to a question that was already kept.
        (variant(), [GOOD], SOURCE, "与已保留的题目文字高度相似"),
        # No source material at all.
        (variant(), None, "   ", "原始资料为空"),
    ],
)
def test_cheap_gates_run_before_any_model_call(monkeypatch, candidate, previous, source, expected):
    fake = Reviewers(monkeypatch)
    passed, rejected = run(candidate, previous=previous, source=source)
    assert passed == []
    assert any(expected in r for r in reasons(rejected))
    assert fake.calls == {"answer": 0, "explanation": 0}


def test_rejected_rows_keep_the_original_candidate(monkeypatch):
    Reviewers(monkeypatch, answer={"selectedAnswers": ["B"]})
    _, rejected = run(GOOD)
    assert rejected[0]["question"] == GOOD
    assert rejected[0]["status"] == "rejected_or_needs_review"
    assert rejected[0]["indexInPart"] == 1
