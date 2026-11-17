"""Real HTTP integration checks against a running Docker trial (no model).

This is a black-box smoke: two independent cookie jars, persisted SQLite
through public APIs, upload preflight failure, privacy and error contracts.
Never accept a non-loopback URL. Do not print cookies or user data.
"""
from __future__ import annotations

from dataclasses import dataclass
from http.cookiejar import CookieJar
import json
import secrets
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


@dataclass
class Response:
    status: int
    headers: object
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class Browser:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, method: str, path: str, *, body=None, content_type=None,
                origin=None) -> Response:
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        if origin is not None:
            headers["Origin"] = origin
        request = Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=15) as reply:
                return Response(reply.status, reply.headers, reply.read(65536))
        except HTTPError as error:
            with error:
                return Response(error.code, error.headers, error.read(65536))

    def api(self, method: str, path: str, *, payload=None, origin=None) -> Response:
        body = None if payload is None else json.dumps(
            payload, ensure_ascii=False).encode("utf-8")
        return self.request(method, path, body=body,
                            content_type="application/json" if body else None,
                            origin=origin)


def assert_status(response: Response, status: int, context: str) -> None:
    assert response.status == status, (
        f"{context}: expected HTTP {status}, received {response.status}")


def assert_error(response: Response, status: int, code: str, context: str) -> None:
    assert_status(response, status, context)
    data = response.json()
    assert data["error"]["code"] == code, context + ": incorrect stable error code"
    assert data["error"]["requestId"] == response.headers.get("X-Request-ID"), (
        context + ": correlation ID mismatch")
    assert response.headers.get("Cache-Control") == "no-store", (
        context + ": cacheable private error")


def multipart(fields: dict[str, str], content: bytes) -> tuple[bytes, str]:
    boundary = "zhixueban-" + secrets.token_hex(12)
    parts = []
    for name, value in fields.items():
        assert name.isascii() and '"' not in name
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
            f"\r\n\r\n{value}\r\n".encode("utf-8"))
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; '
        'name="files"; filename="generic-lesson.txt"\r\n'
        'Content-Type: text/plain\r\n\r\n'.encode("ascii")
        + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def library_ids(browser: Browser) -> set[str]:
    reply = browser.api("GET", "/api/libraries")
    assert_status(reply, 200, "read libraries")
    return {library["id"] for library in reply.json()["libraries"]}


def exercise(base: str) -> None:
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or (
            parsed.path or parsed.query or parsed.fragment or parsed.username):
        raise ValueError("Container smoke is permitted only against loopback HTTP")
    origin = base.rstrip("/")
    anonymous = Browser(origin)
    a, b = Browser(origin), Browser(origin)

    assert_error(anonymous.api("GET", "/api/libraries"),
                 401, "AUTH_REQUIRED", "unauthenticated libraries")
    for browser in (a, b):
        page = browser.request("GET", "/")
        assert_status(page, 200, "new browser session")
        assert len(browser.cookies) == 1, "session cookie was not issued"
    assert tuple(c.value for c in a.cookies) != tuple(c.value for c in b.cookies), (
        "two browsers must not share the same session")

    initial_a, initial_b = library_ids(a), library_ids(b)
    assert initial_a == initial_b, "new browser spaces should start from same template"
    assert_status(a.api("PUT", "/api/libraries/phase44-a",
                        payload={"title": "自主学习资料"}, origin=origin),
                  200, "create learning library A")
    assert "phase44-a" in library_ids(a)
    assert "phase44-a" not in library_ids(b), "library leaked to browser B"

    assert_status(b.api("PUT", "/api/libraries/phase44-b",
                        payload={"title": "跨领域学习"}, origin=origin),
                  200, "create learning library B")
    assert "phase44-b" in library_ids(b)
    assert "phase44-b" not in library_ids(a), "library leaked to browser A"

    forbidden = a.api("PUT", "/api/libraries/phase44-illegal",
                      payload={"title": "invalid origin"},
                      origin="https://untrusted.invalid")
    assert_error(forbidden, 403, "FORBIDDEN", "cross-site mutation")
    assert "phase44-illegal" not in library_ids(a)

    service = a.api("GET", "/api/health")
    assert_status(service, 200, "model readiness status")
    assert service.json()["generationReady"] is False, (
        "the deliberate model-free smoke must not report AI as available")

    body, kind = multipart(
        {"libraryId": "phase44-a", "libraryName": "自主学习资料",
         "questionCount": "1", "requirements": "针对学习资料生成一道选择题"},
        b"A general lesson may contain facts, explanations, and examples.")
    no_model = a.request("POST", "/api/generation-tasks",
                         body=body, content_type=kind, origin=origin)
    assert_error(no_model, 503, "SERVICE_UNAVAILABLE",
                 "upload when inference unavailable")

    for browser in (a, b):
        response = browser.api("GET", "/api/generation-tasks")
        assert_status(response, 200, "list tasks after rejected preflight")
        assert response.json()["tasks"] == [], (
            "rejected upload must not create a queued or saved task")
    assert "phase44-a" in library_ids(a)
    assert "phase44-b" in library_ids(b)

    print("PASS: two isolated live browser sessions; independent knowledge libraries;")
    print("PASS: origin enforcement and stable request IDs;")
    print("PASS: model unavailable => HTTP 503 without creating a generation task.")
    print("LIMIT: No Ollama/Qwen generation, queue execution, Compose HTTPS, Android.")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python scripts/container_http_smoke.py http://127.0.0.1:18080",
              file=sys.stderr)
        return 2
    exercise(argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
