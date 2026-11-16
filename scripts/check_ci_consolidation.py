"""Static CI consolidation audit for the integrated release candidate.

This guard deliberately checks only the worktree and never changes workflows,
branch settings or release state. Use with the full release CI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

RETAINED = frozenset({"stable-quality-gate.yml", "web-ci.yml"})
REQUIRED_STEPS = (
    "Check that the candidate contains the main baseline",
    "Build Web frontend",
    "Install Python requirements",
    "Test integration audit and verify pinned PR ancestry",
    "Test Agent runtime and study planning",
    "Test deterministic backend quality and job lifecycle",
    "Test ZIP verifier failure cases",
    "Package Web trial and validate source archive",
    "Summarize candidate (no source ZIP uploaded)",
)


def audit(root: Path) -> dict:
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        raise ValueError("Missing GitHub Actions workflow directory")
    actual = {
        file.name for file in workflows.iterdir()
        if file.is_file() and file.suffix in {".yml", ".yaml"}
    }
    if actual != RETAINED:
        raise ValueError(
            "Unexpected CI workflow set; "
            f"missing={sorted(RETAINED - actual)}, extra={sorted(actual - RETAINED)}"
        )
    stable = (workflows / "stable-quality-gate.yml").read_text(encoding="utf-8")
    legacy = (workflows / "web-ci.yml").read_text(encoding="utf-8")
    if stable.count("    name: Stable quality / Web + Agent + ZIP") != 1:
        raise ValueError("Missing or duplicated stable check name")
    for step in REQUIRED_STEPS:
        if stable.count("      - name: " + step) != 1:
            raise ValueError("Missing or duplicated stable gate step: " + step)
    if "  workflow_call:" not in stable or "  workflow_dispatch:" not in stable:
        raise ValueError("Stable gate must support reuse and manual verification")
    if "cancel-in-progress: true" not in stable:
        raise ValueError("Stable CI must cancel superseded runs")
    if "fetch-depth: 0" not in stable:
        raise ValueError("Ancestry audit requires complete git history")
    if "permissions:\n  contents: read" not in stable:
        raise ValueError("Stable gate must use read-only repository permissions")
    if "    branches: [main]" not in legacy:
        raise ValueError("Original main branch CI was unexpectedly changed")
    if "name: Web CI" not in legacy:
        raise ValueError("Original main CI check was unexpectedly changed")

    return {
        "schemaVersion": 1,
        "retainedWorkflows": sorted(actual),
        "removedStageOnlyWorkflows": 8,
        "stableQualitySteps": len(REQUIRED_STEPS),
        "mainCiPreserved": True,
        "limitations": [
            "Only static CI structure was checked; required checks are not enabled",
            "The main branch was not changed and no pull requests were merged",
            "Real Docker/Qwen inference/Android validation remains outstanding",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(args.root)
    except (OSError, ValueError) as error:
        print("CI CONSOLIDATION FAILED: " + str(error), file=sys.stderr)
        return 1
    data = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data, encoding="utf-8")
    print(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
