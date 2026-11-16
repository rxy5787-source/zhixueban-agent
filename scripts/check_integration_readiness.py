"""Offline audit of a stacked Git release candidate.

Run after checkout with complete history:
    python scripts/check_integration_readiness.py --manifest docs/integration/phase40.json

This audits ancestry and records review gates; it does NOT merge branches,
compare semantic feature parity, or claim release readiness.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REQUIRED_FIELDS = ("schemaVersion", "baseline", "spine", "sideBranches")


def ancestor(older: str, newer: str) -> bool:
    command = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        capture_output=True, text=True, check=False,
    )
    if command.returncode == 0:
        return True
    if command.returncode == 1:
        return False
    raise RuntimeError("Cannot inspect git ancestry: " + command.stderr.strip())


def verify(manifest: dict, candidate: str = "HEAD") -> dict:
    if any(field not in manifest for field in REQUIRED_FIELDS):
        raise ValueError("Incomplete integration manifest")
    if manifest["schemaVersion"] != 1:
        raise ValueError("Unsupported integration manifest version")
    baseline = manifest["baseline"]
    spine = manifest["spine"]
    sides = manifest["sideBranches"]
    if not isinstance(spine, list) or not spine:
        raise ValueError("Missing required mainline ancestry")
    if not isinstance(sides, list):
        raise ValueError("Invalid side branch list")

    failures = []
    if not ancestor(baseline["sha"], candidate):
        failures.append("Candidate does not contain the audited main baseline")
    last = baseline["sha"]
    for entry in spine:
        if not ancestor(last, entry["sha"]):
            failures.append("Mainline parent chain broken at PR #" + str(entry["pr"]))
        if not ancestor(entry["sha"], candidate):
            failures.append("Candidate does not contain PR #" + str(entry["pr"]))
        last = entry["sha"]

    unresolved = []
    integrated = []
    for entry in sides:
        # Branches with diverged histories must not be called merged simply
        # because equivalent code was copied into this release candidate.
        if ancestor(entry["sha"], candidate):
            integrated.append(entry["pr"])
        else:
            unresolved.append({
                "pr": entry["pr"],
                "reason": entry["reason"],
                "status": "needs-diff-and-human-review",
            })
    return {
        "schemaVersion": 1,
        "candidate": candidate,
        "mainlineAncestry": "pass" if not failures else "fail",
        "failures": failures,
        "sideBranchesStillUnmerged": unresolved,
        "sideBranchesAncestors": integrated,
        "shipReady": False,
        "remainingGates": [
            "Human review and approved integration of outstanding PRs",
            "Actual Docker container boot and healthcheck",
            "Real Ollama/Qwen run and source-grounded question quality review",
            "Android physical-device acceptance tests",
        ],
        "disclaimer": "No merges are executed; offline checks do not establish production readiness",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = verify(data)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as e:
        print("INTEGRATION AUDIT FAILED: " + str(e), file=sys.stderr)
        return 1
    formatted = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted, encoding="utf-8")
    print(formatted)
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
