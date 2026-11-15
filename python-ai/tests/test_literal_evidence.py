"""Deterministic quantity checks: parsing, review and template generation.

The generator and the reviewer are written independently, so the round-trip test
(generate a question, then review it against the same source) guards both.
"""

import pytest

from automatic_question_validator import check_structure
from backend import literal_evidence as lit

SOURCE_LINE = "会话空闲超时：30分钟。"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("12", 12),
        ("0", 0),
        ("零", 0),
        ("十", 10),
        ("十二", 12),
        ("二十", 20),
        ("二十三", 23),
        ("两", 2),
        ("百", None),
        ("abc", None),
    ],
)
def test_integer_parses_arabic_and_chinese_numerals(text, expected):
    assert lit.integer(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5分钟", (5, "分钟")),
        ("五分钟", (5, "分钟")),
        (" 3 个 ", (3, "个")),
        ("５分钟", (5, "分钟")),  # full-width digit is normalised
        ("5.5小时", None),
        ("约5分钟", None),
        ("WHERE", None),
    ],
)
def test_quantity_accepts_only_plain_scalar_values(text, expected):
    assert lit.quantity(text) == expected


def _question(stem, values):
    return {
        "question": stem,
        "options": dict(zip("ABCD", values)),
        "answer": "A",
    }


def test_review_quantity_finds_unique_answer_with_verbatim_evidence():
    q = _question("会话空闲超时是多少分钟？", ["15分钟", "30分钟", "45分钟", "60分钟"])
    result = lit.review_quantity(q, SOURCE_LINE)
    assert result["selectedAnswers"] == ["B"]
    assert result["evidenceQuote"] == SOURCE_LINE
    assert (result["value"], result["unit"]) == (30, "分钟")


@pytest.mark.parametrize(
    "stem, values, source",
    [
        # Negated or comparative stems are never judged deterministically.
        ("会话空闲超时不是多少分钟？", ["15分钟", "30分钟", "45分钟", "60分钟"], SOURCE_LINE),
        # Options must be four distinct values in one unit.
        ("会话空闲超时是多少分钟？", ["30分钟", "三十分钟", "45分钟", "60分钟"], SOURCE_LINE),
        ("会话空闲超时是多少分钟？", ["15分钟", "30分钟", "45分钟", "1小时"], SOURCE_LINE),
        # The condition has to appear literally in the question.
        ("登录失败锁定时长是多少分钟？", ["15分钟", "30分钟", "45分钟", "60分钟"], SOURCE_LINE),
        # Conflicting evidence for the same condition means no verdict.
        (
            "会话空闲超时是多少分钟？",
            ["15分钟", "30分钟", "45分钟", "60分钟"],
            SOURCE_LINE + "\n会话空闲超时：45分钟。",
        ),
        # The source says 30 minutes, so "30小时" must not be accepted as supported.
        ("会话空闲超时是多少小时？", ["10小时", "30小时", "45小时", "60小时"], SOURCE_LINE),
    ],
)
def test_review_quantity_declines_when_it_cannot_prove_the_answer(stem, values, source):
    assert lit.review_quantity(_question(stem, values), source) is None


def _points(line):
    return [{"name": "会话超时", "summary": line}]


def test_generated_question_is_reviewed_to_the_same_answer():
    questions = lit.questions_from_facts([SOURCE_LINE], _points(SOURCE_LINE), count=1)
    assert len(questions) == 1
    q = questions[0]
    assert q["options"][q["answer"]] == "30分钟"
    assert len(set(q["options"].values())) == 4
    assert q["explanation"] == SOURCE_LINE
    # Independent reviewer reaches the same answer from the same source.
    review = lit.review_quantity(q, SOURCE_LINE)
    assert review["selectedAnswers"] == [q["answer"]]
    # And the question is structurally acceptable.
    assert check_structure(q) == []


def test_generation_is_deterministic():
    first = lit.questions_from_facts([SOURCE_LINE], _points(SOURCE_LINE), count=1)
    second = lit.questions_from_facts([SOURCE_LINE], _points(SOURCE_LINE), count=1)
    assert first == second


def test_generation_refuses_unsupported_inputs():
    # Higher difficulty levels are not template questions.
    assert lit.questions_from_facts([SOURCE_LINE], _points(SOURCE_LINE), 1, difficulty=2) == []
    # Every line has to be a recognised quantity fact, otherwise the model path handles it.
    mixed = [SOURCE_LINE, "这是一段没有数量的说明文字。"]
    assert lit.questions_from_facts(mixed, _points(SOURCE_LINE), 1) == []
    # An explicit focus that matches no fact must not fall back to unrelated facts.
    assert (
        lit.questions_from_facts(
            [SOURCE_LINE], _points(SOURCE_LINE), 1, requirements="只考登录失败锁定时长"
        )
        == []
    )
