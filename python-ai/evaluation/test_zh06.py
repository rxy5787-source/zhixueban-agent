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


def test_local_redirects_are_rejected_without_following():
    class Redirect:
        status_code = 302

    with pytest.raises(RuntimeError, match="redirect"):
        zh06.checked_local_response(Redirect())


def test_source_revision_is_optional_but_not_a_fabricated_hash(monkeypatch):
    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git")
    monkeypatch.setattr(zh06.subprocess, "run", missing_git)
    assert zh06.code_revision() is None


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



def test_resume_rejects_changed_source_prompt_or_request_id():
    cases = zh06.load_cases()
    case = cases[12]  # SQL mnemonic
    record = {
        "caseId": case["id"], "kind": case["kind"], "sourceSha256": "f" * 64,
        "requestSent": zh06.case_prompt(case), "clientRequestId": "a" * 32,
    }
    zh06.resume_artifact(record, case, "f" * 64)
    with pytest.raises(RuntimeError, match="does not match"):
        zh06.resume_artifact(record, case, "e" * 64)
    with pytest.raises(RuntimeError, match="does not match"):
        zh06.resume_artifact({**record, "clientRequestId": "invalid"}, case, "f" * 64)
    with pytest.raises(RuntimeError, match="does not match"):
        zh06.resume_artifact({**record, "requestSent": "changed prompt"}, case, "f" * 64)


def test_progress_requires_explicit_resume_to_replace(tmp_path):
    path = tmp_path / "case-13.json"
    zh06.write_progress(path, {"runStatus": "prepared"}, permitted=False)
    with pytest.raises(FileExistsError):
        zh06.write_progress(path, {"runStatus": "succeeded"}, permitted=False)
    assert json.loads(path.read_text(encoding="utf-8"))["runStatus"] == "prepared"
    zh06.write_progress(path, {"runStatus": "succeeded"}, permitted=True)
    assert json.loads(path.read_text(encoding="utf-8"))["runStatus"] == "succeeded"


def test_server_receipt_lookup_recovers_task_without_upload():
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"taskId": "b" * 32, "status": "queued"}

    class FakeSession:
        def get(self, path, **kwargs):
            assert path.endswith("/api/generation-submissions/" + "a" * 32)
            assert kwargs["allow_redirects"] is False
            return FakeResponse()

    assert zh06.receipt_for_case(FakeSession(), "http://127.0.0.1:8095", "a" * 32) == "b" * 32


def test_server_receipt_404_does_not_invent_task():
    class MissingSession:
        def get(self, *args, **kwargs):
            return type("NotFound", (), {"status_code": 404})()

    assert zh06.receipt_for_case(MissingSession(), "http://127.0.0.1:8095", "a" * 32) is None


def test_session_cookie_is_saved_without_disclosure(tmp_path):
    from http.cookiejar import Cookie
    import os

    path = tmp_path / ".local-trial.cookies"
    jar = zh06.MozillaCookieJar(str(path))
    jar.set_cookie(Cookie(
        version=0, name="zhixue-trial", value="sensitive-session-token", port=None,
        port_specified=False, domain="127.0.0.1", domain_specified=False,
        domain_initial_dot=False, path="/", path_specified=True, secure=False,
        expires=2000000000, discard=False, comment=None, comment_url=None,
        rest={}, rfc2109=False,
    ))
    zh06.save_private_session(jar)
    assert path.is_file()
    loaded = zh06.MozillaCookieJar(str(path))
    loaded.load()
    assert len(list(loaded)) == 1
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0


def test_plan_cli_does_not_require_source_files(capsys):
    assert zh06.main(["plan"]) == 0
    output = capsys.readouterr().out
    assert "01 [system/mnemonic]" in output
    assert "20 [sql/reply]" in output
