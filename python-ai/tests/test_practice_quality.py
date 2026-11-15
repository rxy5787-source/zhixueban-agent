"""Text clean-up applied before material is sent to the model."""

import pytest

from backend import practice_quality as pq


@pytest.mark.parametrize(
    "text, expected",
    [
        ("A. 选项内容", True),
        ("B、选项内容", True),
        ("问题3: C) 选项内容", True),
        ("WHERE 在分组之前过滤原始数据行。", False),
        ("", False),
        (None, False),
    ],
)
def test_option_rows_are_recognised(text, expected):
    assert pq.is_option_row(text) is expected


def test_usable_text_drops_option_rows_and_detached_fragments():
    material = (
        "WHERE 在分组之前过滤数据行。\nA. 选项一\n还有一个原因是效率更高\n第二段正文内容在这里。"
    )
    assert pq.usable_practice_text(material).splitlines() == [
        "WHERE 在分组之前过滤数据行。",
        "第二段正文内容在这里。",
    ]


def test_split_keeps_every_unit_and_respects_the_limit():
    units = [f"这是第{i}个完整的资料句子，包含足够的文字。" for i in range(1, 9)]
    parts = list(pq.split_practice_text("".join(units), limit=60))
    assert len(parts) > 1
    assert all(len(part) <= 60 for part in parts)
    assert "".join(parts).replace("\n", "") == "".join(units)


@pytest.mark.parametrize(
    "stem, evidence, expected_issue",
    [
        ("第3题的正确答案是？", "正文内容在这里足够长。", "题号"),
        ("下面哪种排序方法最快？", "快速排序平均需要线性对数时间。", "比较题缺少可检验的判断标准"),
        ("哪个子句过滤分组后的结果？", "A. HAVING", "只有原资料的选项"),
        ("哪个子句过滤分组后的结果？", "还有一个原因是效率更高", "脱离上下文"),
    ],
)
def test_standalone_issue_flags_unanswerable_stems(stem, evidence, expected_issue):
    assert expected_issue in pq.standalone_issue(stem, evidence)


def test_standalone_issue_is_empty_for_a_self_contained_question():
    assert (
        pq.standalone_issue(
            "HAVING 子句作用于分组前还是分组后？", "HAVING 在分组之后过滤聚合结果。"
        )
        == ""
    )
