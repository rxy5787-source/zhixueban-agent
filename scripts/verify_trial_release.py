"""Conservative ZIP release gate for the private Zhixueban Web trial.

Offline/static validation only. This does NOT prove Docker boots, model
accuracy, live capacity, Android device compatibility or production security.
Usage: python scripts/verify_trial_release.py path/to/archive.zip --manifest path.json
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

REQUIRED = {
    "compose.yaml",
    "Dockerfile",
    "Caddyfile",
    ".env.example",
    "README.md",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/src/main.tsx",
    "server/requirements.txt",
    "server/generate_from_file.py",
    "server/backend/__init__.py",
    "server/backend/web_trial.py",
    "server/backend/web_api.py",
    "server/backend/web_error_contract.py",
    "server/backend/agent_runtime.py",
    "server/backend/weak_points_skill.py",
    "server/backend/study_skill_planner.py",
    "server/backend/study_plan_service.py",
    "server/backend/study_practice_executor.py",
    "server/backend/agent_decision_audit.py",
    "server/backend/agent_evaluation.py",
    "server/backend/agent_recovery_policy.py",
    "server/backend/retry_guard.py",
    "server/backend/job_store.py",
    "server/backend/job_timing.py",
    "server/backend/trial_body_limit.py",
    "server/backend/resumable_uploads.py",
    "server/backend/trial_access.html",
    "server/backend/study_chat.py",
}

# Non-source data and developer/private material must never ship in the ZIP.
BLOCKED_SEGMENTS = {
    ".git", ".github", ".venv", "venv", "__pycache__", ".pytest_cache",
    "node_modules", "tests", "test-results", "coverage", "artifacts",
    "uploads", ".ssh", ".aws",
}
BLOCKED_EXACT = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
BLOCKED_EXTENSIONS = {".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx", ".pyc"}
MAX_MEMBERS = 2000
MAX_UNCOMPRESSED = 150 * 1024 * 1024
MAX_MEMBER = 30 * 1024 * 1024


def inspect_archive(archive: Path) -> dict:
    if not archive.is_file() or not zipfile.is_zipfile(archive):
        raise ValueError("Not a valid ZIP archive")
    members = {}
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("Too many archive entries")
        total = 0
        for info in infos:
            raw = info.filename
            if "\\" in raw or "\x00" in raw or raw.startswith("/"):
                raise ValueError("Unsafe ZIP entry path")
            name = raw.rstrip("/")
            parts = name.split("/")
            if any(part in ("", ".", "..") for part in parts):
                raise ValueError("Unsafe ZIP entry path")
            # Do not allow symbolic links that might escape a deployment root.
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("Archive contains a symbolic link")
            if any(part.lower() in BLOCKED_SEGMENTS for part in parts):
                raise ValueError("Archive contains developer or runtime data")
            if any(part.lower() in BLOCKED_EXACT for part in parts):
                raise ValueError("Archive contains a credential candidate")
            if Path(name).suffix.lower() in BLOCKED_EXTENSIONS:
                raise ValueError("Archive contains a private or compiled file")
            if name in members:
                raise ValueError("Duplicate ZIP path")
            if info.file_size > MAX_MEMBER:
                raise ValueError("Oversize ZIP member")
            total += info.file_size
            if total > MAX_UNCOMPRESSED:
                raise ValueError("Oversize uncompressed ZIP")
            members[name] = info

        missing = sorted(REQUIRED - members.keys())
        if missing:
            raise ValueError("Missing required release files: " + ", ".join(missing))

        py_entries = sorted(
            name for name, info in members.items()
            if name.startswith("server/") and name.endswith(".py") and not info.is_dir()
        )
        for name in py_entries:
            with zf.open(members[name]) as stream:
                source = stream.read()
            try:
                ast.parse(source, filename=name)
            except (SyntaxError, UnicodeError, ValueError) as error:
                raise ValueError("Invalid packaged Python source: " + name) from error

        # These imports must resolve from the *packaged* tree, not from
        # accidentally present files in the checkout.
        trial = zf.read("server/backend/web_trial.py").decode("utf-8")
        if "from .web_error_contract import" not in trial:
            raise ValueError("Packaged Web API is missing the error contract")
        if "from .job_timing import" not in trial:
            raise ValueError("Packaged Web API is missing task observability")
        if "from .agent_recovery_policy import" not in trial:
            raise ValueError("Packaged Web API is missing recovery policy")

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    return {
        "schemaVersion": 1,
        "artifact": archive.name,
        "sha256": digest,
        "fileCount": len(members),
        "pythonFilesParsed": len(py_entries),
        "uncompressedBytes": total,
        "gate": "offline-structure-and-python-syntax-only",
        "limitations": [
            "No Docker/image build or running container was tested",
            "No real Ollama/Qwen inference or model quality was measured",
            "No Android physical device validation was performed",
            "Archive hash identifies this build, not a reproducible build claim",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect_archive(args.archive)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print("RELEASE GATE FAILED: " + str(error), file=sys.stderr)
        return 1
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
