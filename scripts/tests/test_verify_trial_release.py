"""Deterministic tests for release ZIP verification, no Qwen or Docker."""
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_trial_release.py"
spec = importlib.util.spec_from_file_location("verify_trial_release", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

GOOD = {key: b"placeholder" for key in gate.REQUIRED}
GOOD.update({
    "server/backend/web_trial.py": (
        b"from .web_error_contract import error_code\n"
        b"from .job_timing import timing_report\n"
        b"from .agent_recovery_policy import advise_recovery\n"
    ),
    "server/backend/web_api.py": b"pass\n",
    "server/backend/__init__.py": b"",
    "server/generate_from_file.py": b"pass\n",
})


def archive(tmp_path, changes=None, removed=()):
    path = tmp_path / "candidate.zip"
    files = dict(GOOD)
    for key in removed:
        del files[key]
    files.update(changes or {})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def test_good_release_has_auditable_hash_and_static_gate(tmp_path):
    path = archive(tmp_path)
    result = gate.inspect_archive(path)
    assert result["fileCount"] == len(GOOD)
    assert result["pythonFilesParsed"] >= 3
    assert len(result["sha256"]) == 64
    assert result["gate"] == "offline-structure-and-python-syntax-only"
    assert any("Qwen" in text for text in result["limitations"])


@pytest.mark.parametrize("dangerous", [
    ".env", "server/private.sqlite3", "server/backend/__pycache__/x.pyc",
    "frontend/node_modules/lib.js", "server/backend/../../secret.txt",
    "server/backend/keys.pem", "server/backend/app.key", "server/.git/config",
    "server\\..\\secret.txt",
])
def test_private_or_unsafe_member_is_rejected(tmp_path, dangerous):
    path = archive(tmp_path, {dangerous: b"secret"})
    with pytest.raises(ValueError):
        gate.inspect_archive(path)


def test_missing_required_runtime_module_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Missing required"):
        gate.inspect_archive(archive(tmp_path, removed=["server/backend/web_error_contract.py"]))


def test_malformed_packaged_python_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Invalid packaged Python"):
        gate.inspect_archive(archive(tmp_path, {"server/backend/web_api.py": b"def bad(:\n"}))


def test_not_a_zip_is_rejected(tmp_path):
    path = tmp_path / "not-a-zip.zip"
    path.write_bytes(b"invalid")
    with pytest.raises(ValueError, match="Not a valid ZIP"):
        gate.inspect_archive(path)
