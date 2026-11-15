"""Offline contract tests for the ZH-06 quality-evaluation runner.

No Ollama or HTTP server is used by this suite.
"""
import csv
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).with_name("zh06.py")
SPEC = importlib.util.spec_from_file_location("zh06_tested", SCRIPT)
zh06 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = zh06
SPEC.loader.exec_module(zh06)


def test_suite_exactly_matches_original_twenty_cases():
    cases = zh06.load_cases()
    assert len(cases) == 20
    assert [case["id"] for case in cases] == list(range(1, 21))
    assert {case["group"] for case in cases} == {"system", "sql"}
    assert [c["id"] for c in cases if c["negative"]] == [20]
    assert {kind: sum(c["kind"] == kind for c in cases) for kind in ("mnemonic", "reply", "cloze", "single_choice")} == {
        "mnemonic": 5, "reply": 5, "cloze": 4, "single_choice": 6,
    }


def test_runtime_prompts_are_direct_questions_without_answer_key_leakage():
    cases = zh06.load_cases()
    assert zh06.case_prompt(cases[0]).startswith("请根据资料编写一条便于回忆的记忆口诀：")
    assert zh06.case_prompt(cases[16]).startswith("请根据资料生成一道四选一单选题：")
    negative = zh06.case_prompt(cases[19])
    assert "TCP" in negative and "SQL" in negative
    assert "拒绝" not in negative
    assert "不得用 SQL 原文冒充依据" not in negative
    assert cases[19]["negative"] is True


def test_suite_fails_closed_on_missing_or_duplicate_questions(tmp_path):
    content = zh06.SUITE.read_text(encoding="utf-8")
    altered = tmp_path / "suite.md"
    altered.write_text(content.replace("20. 缺失依据", "21. 缺失依据"), encoding="utf-8")
    with pytest.raises(ValueError):
        zh06.load_cases(altered)
    altered.write_text(content.replace("13. 口诀", "12. 口诀"), encoding="utf-8")
    with pytest.raises(ValueError):
        zh06.load_cases(altered)


@pytest.mark.parametrize("value", [
    "https://localhost:8095", "http://example.com:8095",
    "http://127.0.0.1:8095/api", "http://127.0.0.1",
    "http://localhost:8095?x=1", "http://user@localhost:8095",
])
def test_live_runner_rejects_non_loopback_or_ambiguous_urls(value):
    with pytest.raises(ValueError):
        zh06.loopback_origin(value)


def test_live_runner_accepts_explicit_loopback():
    assert zh06.loopback_origin("http://127.0.0.1:8095/") == "http://127.0.0.1:8095"
    assert zh06.loopback_origin("http://localhost:8095") == "http://localhost:8095"


def test_review_denominators_ignore_missing_and_unjudged(tmp_path):
    artifacts = {
        1: {"caseId": 1, "runStatus": "succeeded", "elapsedWallMs": 3000},
        2: {"caseId": 2, "runStatus": "failed", "elapsedWallMs": 5000},
        3: {"caseId": 3, "runStatus": "still_running_at_timeout", "elapsedWallMs": 500},
        20: {"caseId": 20, "runStatus": "failed", "elapsedWallMs": 1200},
    }
    reviews = {
        1: {"reviewed": "yes", "facts_correct": "yes", "source_supported": "no",
            "goal_covered": "yes", "usable": "no"},
        2: {"reviewed": "no", "facts_correct": "yes", "source_supported": "yes",
            "goal_covered": "yes", "usable": "yes"},
        3: {"reviewed": "yes", "facts_correct": "yes", "source_supported": "yes",
            "goal_covered": "yes", "usable": "yes"},
        20: {"reviewed": "yes", "refusal_correct": "yes"},
    }
    report = zh06.build_report(artifacts, reviews)
    assert report["expectedCases"] == 20
    assert report["attemptedCases"] == 4
    assert report["terminalCases"] == 3
    assert report["humanReviewedCases"] == 2
    assert report["humanUsability"] == {"numerator": 0, "denominator": 1, "rate": 0.0}
    assert report["factualCorrectness"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert report["sourceSupport"] == {"numerator": 0, "denominator": 1, "rate": 0.0}
    assert report["correctRefusal"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert report["medianTaskWallMs"] == 3000
    assert report["modelCallCount"] is None


def test_empty_artifacts_produce_null_rates_without_fake_scores(tmp_path):
    output = tmp_path / "new-run"
    zh06.report(output)
    result = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert result["attemptedCases"] == 0
    assert result["terminalCases"] == 0
    assert result["humanUsability"]["rate"] is None
    assert result["medianTaskWallMs"] is None
    assert "尚无人工有效样本" in (output / "report.md").read_text(encoding="utf-8")


def test_manual_csv_is_not_overwritten(tmp_path):
    out = tmp_path / "run"
    zh06.write_json(out / "case-13.json", {
        "caseId": 13, "runStatus": "failed", "elapsedWallMs": 1000,
    })
    zh06.review_template(out, zh06.load_cases())
    path = out / "human_review.csv"
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 1
    assert rows[0]["reviewed"] == ""
    assert rows[0]["source_group"] == "sql"
    with pytest.raises(FileExistsError):
        zh06.review_template(out, zh06.load_cases())


def test_run_without_consent_does_not_open_network_or_files(tmp_path):
    from argparse import Namespace
    args = Namespace(
        confirm_live=False, base_url="http://127.0.0.1:8095",
        cases="all", system_source=None, sql_source=zh06.DEFAULT_SQL,
        output=tmp_path, timeout_seconds=30, poll_seconds=1,
    )
    with pytest.raises(ValueError, match="confirm-live"):
        zh06.run_live(args, zh06.load_cases())


def test_duplicate_run_case_cannot_be_silently_overwritten(tmp_path):
    path = tmp_path / "case-01.json"
    zh06.write_json(path, {"caseId": 1})
    with pytest.raises(FileExistsError):
        zh06.write_json(path, {"caseId": 1, "runStatus": "succeeded"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"caseId": 1}


def test_duplicate_review_ids_and_invalid_scores_are_rejected(tmp_path):
    review = tmp_path / "human_review.csv"
    with review.open("w", encoding="utf-8", newline="") as file:
        w = csv.DictWriter(file, fieldnames=zh06.CSV_FIELDS)
        w.writeheader()
        w.writerow({"case_id": 1, "reviewed": "yes", "usable": "maybe"})
    with pytest.raises(ValueError, match="use yes/no/na"):
        zh06.read_reviews(review)


def test_plan_cli_does_not_require_source_files(capsys):
    assert zh06.main(["plan"]) == 0
    output = capsys.readouterr().out
    assert "01 [system/mnemonic]" in output
    assert "20 [sql/reply]" in output
