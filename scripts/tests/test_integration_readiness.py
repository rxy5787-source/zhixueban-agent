"""Unit tests for the phase-40 release ancestry audit (no remote network)."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_integration_readiness.py"
spec = importlib.util.spec_from_file_location("check_integration_readiness", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sample():
    return {
        "schemaVersion": 1,
        "baseline": {"sha": "main"},
        "spine": [{"pr": 14, "sha": "agent"}, {"pr": 42, "sha": "candidate"}],
        "sideBranches": [
            {"pr": 18, "sha": "parallel", "reason": "Old code"},
            {"pr": 25, "sha": "android", "reason": "Device CI"},
        ],
    }


def test_mainline_pass_and_unmerged_side_branches_not_called_integrated(monkeypatch):
    ancestors = {("main", "HEAD"), ("main", "agent"),
                 ("agent", "candidate"), ("agent", "HEAD"),
                 ("candidate", "HEAD")}
    monkeypatch.setattr(mod, "ancestor", lambda a, b: (a, b) in ancestors)
    report = mod.verify(sample())
    assert report["mainlineAncestry"] == "pass"
    assert report["failures"] == []
    assert [x["pr"] for x in report["sideBranchesStillUnmerged"]] == [18, 25]
    assert report["sideBranchesAncestors"] == []
    assert report["shipReady"] is False
    assert len(report["remainingGates"]) >= 3


def test_detects_missing_mainline_commit(monkeypatch):
    ancestors = {("main", "HEAD"), ("main", "agent"),
                 ("agent", "candidate"), ("agent", "HEAD")}
    monkeypatch.setattr(mod, "ancestor", lambda a, b: (a, b) in ancestors)
    report = mod.verify(sample())
    assert report["mainlineAncestry"] == "fail"
    assert any("PR #42" in reason for reason in report["failures"])


def test_detects_broken_parent_chain(monkeypatch):
    ancestors = {("main", "HEAD"), ("main", "agent"),
                 ("agent", "HEAD"), ("candidate", "HEAD")}
    monkeypatch.setattr(mod, "ancestor", lambda a, b: (a, b) in ancestors)
    report = mod.verify(sample())
    assert report["mainlineAncestry"] == "fail"
    assert any("parent chain" in reason for reason in report["failures"])


def test_new_side_branch_ancestor_classified_without_implicit_release_approval(monkeypatch):
    monkeypatch.setattr(mod, "ancestor", lambda a, b: True)
    report = mod.verify(sample())
    assert report["sideBranchesStillUnmerged"] == []
    assert report["sideBranchesAncestors"] == [18, 25]
    assert report["shipReady"] is False


@pytest.mark.parametrize("data", [
    {},
    {"schemaVersion": 9, "baseline": {"sha": "m"}, "spine": [{"pr": 1, "sha": "s"}], "sideBranches": []},
    {"schemaVersion": 1, "baseline": {"sha": "m"}, "spine": [], "sideBranches": []},
])
def test_invalid_manifests_rejected(data):
    with pytest.raises(ValueError):
        mod.verify(data)
