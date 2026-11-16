"""Tests for safe deduplication of phase-only GitHub workflows."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_ci_consolidation.py"
spec = importlib.util.spec_from_file_location("check_ci_consolidation", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

STABLE = """name: Stable candidate quality gate
  workflow_dispatch:
  workflow_call:
concurrency:
  cancel-in-progress: true
permissions:
  contents: read
      - uses: actions/checkout@v6
          fetch-depth: 0
  stable-quality:
    name: Stable quality / Web + Agent + ZIP
"""
STABLE += "".join(f"      - name: {name}\n" for name in mod.REQUIRED_STEPS)
LEGACY = "name: Web CI\non:\n  pull_request:\n    branches: [main]\n"


def make_root(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "stable-quality-gate.yml").write_text(STABLE, encoding="utf-8")
    (wf / "web-ci.yml").write_text(LEGACY, encoding="utf-8")
    return tmp_path, wf


def test_expected_minimal_ci_set_is_accepted(tmp_path):
    root, _ = make_root(tmp_path)
    report = mod.audit(root)
    assert report["mainCiPreserved"] is True
    assert report["retainedWorkflows"] == ["stable-quality-gate.yml", "web-ci.yml"]
    assert report["removedStageOnlyWorkflows"] == 8


@pytest.mark.parametrize("extra", ["phase40-integration-readiness.yml", "phase39-release-candidate.yml"])
def test_rejects_residual_phase_workflow(tmp_path, extra):
    root, wf = make_root(tmp_path)
    (wf / extra).write_text("name: old\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected CI workflow set"):
        mod.audit(root)


def test_rejects_missing_main_ci(tmp_path):
    root, wf = make_root(tmp_path)
    (wf / "web-ci.yml").unlink()
    with pytest.raises(ValueError, match="Unexpected CI workflow set"):
        mod.audit(root)


def test_rejects_dropped_release_step(tmp_path):
    root, wf = make_root(tmp_path)
    path = wf / "stable-quality-gate.yml"
    path.write_text(STABLE.replace("      - name: Package Web trial and validate source archive\n", ""),
                    encoding="utf-8")
    with pytest.raises(ValueError, match="Missing or duplicated stable gate step"):
        mod.audit(root)


def test_rejects_broadened_ci_permissions(tmp_path):
    root, wf = make_root(tmp_path)
    path = wf / "stable-quality-gate.yml"
    path.write_text(STABLE.replace("  contents: read", "  contents: write"),
                    encoding="utf-8")
    with pytest.raises(ValueError, match="read-only"):
        mod.audit(root)


def test_rejects_removed_main_branch_trigger(tmp_path):
    root, wf = make_root(tmp_path)
    path = wf / "web-ci.yml"
    path.write_text(LEGACY.replace("    branches: [main]", "    branches: [release]"),
                    encoding="utf-8")
    with pytest.raises(ValueError, match="main branch"):
        mod.audit(root)
