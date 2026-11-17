"""Real Docker *replacement* persistence smoke (no user files or Qwen).

Run as two phases with the same temporary runner-only cookie storage:
  python scripts/container_restart_smoke.py seed http://127.0.0.1:18080 DIR
  # a CI-only fixture inserts a synthetic running task; replace the container
  python scripts/container_restart_smoke.py verify http://127.0.0.1:18080 DIR

The state directory is ephemeral and MUST NEVER be uploaded as an artifact.
"""
from __future__ import annotations

from http.cookiejar import MozillaCookieJar
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, build_opener

from container_http_smoke import Browser, assert_error, assert_status, library_ids


def browser(base: str, jar: Path, *, reopen=False) -> Browser:
    result = Browser(base)
    result.cookies = MozillaCookieJar(str(jar))
    if reopen:
        result.cookies.load(ignore_discard=True, ignore_expires=True)
    result.opener = build_opener(HTTPCookieProcessor(result.cookies))
    return result


def safe_path(base: str, directory: Path) -> str:
    url = urlsplit(base)
    if (url.scheme != "http" or url.hostname != "127.0.0.1"
            or url.path or url.query or url.fragment or url.username):
        raise ValueError("Only loopback HTTP is permitted for the restart smoke")
    if directory.is_symlink():
        raise ValueError("Do not follow symlinked state directories")
    return base.rstrip("/")


def seed(base: str, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    spaces = {}
    for name, ident in (("alpha", "phase45-alpha"), ("beta", "phase45-beta")):
        agent = browser(base, directory / (name + ".cookies"))
        assert_status(agent.request("GET", "/"), 200, "seed browser " + name)
        assert len(agent.cookies) == 1, "missing signed browser session"
        cookie = next(iter(agent.cookies))
        space_id = cookie.value.split(".")[0]
        assert len(space_id) == 48 and all(c in "0123456789abcdef" for c in space_id)
        assert_status(agent.api("PUT", "/api/libraries/" + ident,
                                payload={"title": "通用学习资料 " + name}, origin=base),
                      200, "create persistent library")
        assert ident in library_ids(agent), "new library not visible"
        spaces[name + "Space"] = space_id
        agent.cookies.save(ignore_discard=True, ignore_expires=True)
        os.chmod(directory / (name + ".cookies"), 0o600)
    a = browser(base, directory / "alpha.cookies", reopen=True)
    b = browser(base, directory / "beta.cookies", reopen=True)
    assert "phase45-beta" not in library_ids(a)
    assert "phase45-alpha" not in library_ids(b)
    state = directory / "state.json"
    state.write_text(json.dumps(spaces, sort_keys=True), encoding="utf-8")
    os.chmod(state, 0o600)
    print("PASS: two independent signed sessions and libraries seeded to persistent Docker volume")


def verify(base: str, directory: Path) -> None:
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    task = state["taskId"]
    assert len(task) == 32 and all(c in "0123456789abcdef" for c in task)
    a = browser(base, directory / "alpha.cookies", reopen=True)
    b = browser(base, directory / "beta.cookies", reopen=True)

    # These are existing signed cookies, not newly established sessions.
    assert "phase45-alpha" in library_ids(a), "alpha library did not survive replacement"
    assert "phase45-beta" in library_ids(b), "beta library did not survive replacement"
    assert "phase45-beta" not in library_ids(a), "beta library leaked to alpha"
    assert "phase45-alpha" not in library_ids(b), "alpha library leaked to beta"

    endpoint = "/api/generation-tasks/" + task
    assert_error(b.api("GET", endpoint), 404, "NOT_FOUND", "cross-space task read")
    assert_error(b.api("GET", endpoint + "/recovery-advice"),
                 404, "NOT_FOUND", "cross-space recovery")
    assert_error(b.api("GET", endpoint + "/timing"),
                 404, "NOT_FOUND", "cross-space timing")

    deadline = time.monotonic() + 20
    while True:
        response = a.api("GET", endpoint)
        assert_status(response, 200, "recovered task read")
        if response.json()["status"] == "interrupted":
            break
        if time.monotonic() >= deadline:
            raise AssertionError("running task was not marked interrupted after restart")
        time.sleep(0.2)
    job = response.json()
    assert job["files"] == [{"name": "synthetic.txt", "status": "parsing"}], (
        "checkpoint was not persisted across replacement")
    assert job["taskId"] == task and job["libraryId"] == "phase45-alpha"
    advice = a.api("GET", endpoint + "/recovery-advice")
    assert_status(advice, 200, "recovery advice after restart")
    diag = a.api("GET", endpoint + "/timing")
    assert_status(diag, 200, "timing after restart")
    assert diag.json()["state"] == "interrupted"
    assert "synthetic.txt" not in diag.body.decode("utf-8")
    assert_error(b.api("POST", endpoint + "/retry", origin=base),
                 404, "NOT_FOUND", "cross-space retry")

    first = a.api("POST", endpoint + "/retry", origin=base)
    assert_status(first, 202, "restart recovery retry")
    child = first.json()["taskId"]
    assert child != task
    duplicate = a.api("POST", endpoint + "/retry", origin=base)
    assert_status(duplicate, 202, "duplicate retry")
    assert duplicate.json()["taskId"] == child, "retry created a duplicate task"
    assert_error(b.api("GET", "/api/generation-tasks/" + child),
                 404, "NOT_FOUND", "cross-space retry task")

    tasks = a.api("GET", "/api/generation-tasks")
    assert_status(tasks, 200, "task listing after retry")
    ids = [job["taskId"] for job in tasks.json()["tasks"]]
    assert sorted(ids) == sorted((task, child)), (
        "recovery produced unexpected extra or missing jobs")
    assert a.api("GET", endpoint).json()["status"] == "interrupted"
    assert a.api("GET", "/api/health").json()["generationReady"] is False
    print("PASS: data and signed sessions survive Docker container replacement")
    print("PASS: interrupted task recovery retains checkpoints and isolated diagnostics")
    print("PASS: one retry idempotently reuses its task; other visitor cannot access it")
    print("LIMIT: fixture simulated an interrupted worker; no actual Qwen inference")


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in ("seed", "verify"):
        print("Usage: container_restart_smoke.py seed|verify http://127.0.0.1:18080 DIR",
              file=sys.stderr)
        return 2
    directory = Path(argv[3])
    base = safe_path(argv[2], directory)
    if argv[1] == "seed":
        seed(base, directory)
    else:
        verify(base, directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
