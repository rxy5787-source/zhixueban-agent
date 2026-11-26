"""Run with the packaged backend on PYTHONPATH. Live tests require the test Spring service URL."""

import os
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
import requests

from backend import account_web, config
from backend.web_trial import create_app


ORIGIN = "https://account.test"
ACCOUNT_COOKIE = "__Host-zhixue-account"
GUEST_COOKIE = "__Host-zhixue-trial"
HEADERS = {"Origin": ORIGIN, "X-Zhixue-Account": "1"}
MATERIAL = {"title": "DNS", "text": "Recursive resolvers cache DNS answers."}


def browser_at(tmp_path, *, enabled=True):
    frontend = tmp_path / "public"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text("<title>Account test</title>")
    app = create_app(tmp_path / "data", frontend, ORIGIN, "test-secret-" * 4,
                     start_worker=False, account_login=enabled)
    return TestClient(app, base_url=ORIGIN)


@pytest.fixture
def live_auth(monkeypatch):
    url = os.environ.get("ZHIXUE_TEST_AUTH_URL")
    if not url:
        pytest.skip("Set ZHIXUE_TEST_AUTH_URL to an isolated Spring Boot test instance")
    assert url.startswith("http://127.0.0.1:"), "Use an isolated loopback fixture"
    monkeypatch.setattr(config, "AUTH_URL", url)

    def register(token_details=False):
        credentials = {"username": "test_" + uuid4().hex[:18], "password": "Synthetic-test-password_521"}
        response = requests.post(url + "/api/auth/register", json=credentials, timeout=15)
        assert response.status_code == 200
        return (credentials, response.json()) if token_details else credentials

    return register


def test_real_login_refresh_logout_and_material_authorization(tmp_path, live_auth):
    credentials_a, credentials_b = live_auth(), live_auth()
    with browser_at(tmp_path) as browser:
        assert browser.get("/account").status_code == 200
        assert browser.get("/").status_code == 200
        guest = browser.cookies.get(GUEST_COOKIE)
        assert guest
        assert browser.get("/api/account/materials").status_code == 401
        credentials_wrong = {**credentials_a, "password": "Synthetic-wrong-password"}
        assert browser.post("/api/account/login", json=credentials_wrong, headers=HEADERS).status_code == 401
        response = browser.post("/api/account/login", json=credentials_a, headers=HEADERS)
        assert response.status_code == 200 and response.json() == {"username": credentials_a["username"]}
        assert response.headers["cache-control"] == "no-store"
        cookie_header = response.headers["set-cookie"].lower()
        assert all(attribute in cookie_header for attribute in ("secure", "httponly", "samesite=lax", "path=/", "max-age"))
        assert "domain=" not in cookie_header
        assert browser.get("/api/account/session").json() == response.json()
        token_before_logout = browser.cookies.get(ACCOUNT_COOKIE)
        created = browser.post("/api/account/materials", json=MATERIAL, headers=HEADERS)
        assert created.status_code == 201
        id_a = created.json()["id"]
        assert browser.post("/api/account/logout", headers=HEADERS).status_code == 204
        assert browser.cookies.get(GUEST_COOKIE) == guest
        assert browser.get("/api/libraries").status_code == 200
        assert browser.get("/api/account/materials", headers={
            "Cookie": f"{ACCOUNT_COOKIE}={token_before_logout}; {GUEST_COOKIE}={guest}",
        }).status_code == 401

        assert browser.post("/api/account/login", json=credentials_b, headers=HEADERS).status_code == 200
        assert browser.get("/api/account/materials?user_id=other&space_id=other").json() == []
        foreign = "/api/account/materials/" + id_a
        assert browser.get(foreign).status_code == 404
        assert browser.put(foreign, json=MATERIAL, headers=HEADERS).status_code == 404
        assert browser.delete(foreign, headers=HEADERS).status_code == 404
        assert browser.post("/api/account/materials", json={**MATERIAL, "user_id": "other"}, headers=HEADERS).status_code == 422
        independent = browser.post("/api/account/materials", json={**MATERIAL, "title": "B only"}, headers=HEADERS)
        assert independent.status_code == 201
        assert browser.post("/api/account/logout", headers=HEADERS).status_code == 204

        assert browser.post("/api/account/login", json=credentials_a, headers=HEADERS).status_code == 200
        assert [item["id"] for item in browser.get("/api/account/materials").json()] == [id_a]
        assert browser.get(foreign).json()["text"] == MATERIAL["text"]
        updated = browser.put(foreign, json={**MATERIAL, "title": "Updated"}, headers=HEADERS)
        assert updated.json()["title"] == "Updated"
        assert browser.delete(foreign, headers=HEADERS).status_code == 204
        assert browser.get(foreign).status_code == 404


def test_real_expired_cookie_remains_denied_with_guest_cookie(tmp_path, live_auth):
    _, session = live_auth(token_details=True)
    expires_in = session["expiresAt"] / 1000 - time.time()
    assert 0 < expires_in <= 61, "Start the test Spring instance with AUTH_SESSION_SECONDS=60"
    with browser_at(tmp_path) as browser:
        assert browser.get("/").status_code == 200
        guest = browser.cookies.get(GUEST_COOKIE)
        headers = {"Cookie": f"{ACCOUNT_COOKIE}={session['token']}; {GUEST_COOKIE}={guest}"}
        assert browser.get("/api/account/session", headers=headers).status_code == 200
        time.sleep(max(0, session["expiresAt"] / 1000 - time.time()) + 0.5)
        assert browser.get("/api/account/materials", headers=headers).status_code == 401
        assert browser.get("/api/libraries").status_code == 200


def test_real_registration_opens_learning_and_keeps_libraries_separate(tmp_path, live_auth):
    username = "learner_" + uuid4().hex[:12]
    credentials = {"username": username, "password": "Synthetic-browser-password_25"}
    other = live_auth()
    endpoint = "/api/libraries/private-study"
    with browser_at(tmp_path) as browser:
        assert browser.get("/").status_code == 200
        assert browser.get("/learn").status_code == 200
        learner = {**HEADERS, "X-Zhixue-Learner": username}
        assert browser.put(endpoint, headers=learner, json={"title": "Private"}).status_code == 401
        assert browser.post("/api/account/register", json=credentials).status_code == 403
        assert browser.post("/api/account/register", json=credentials, headers=HEADERS).status_code == 201
        assert browser.get("/api/account/session").json() == {"username": username}
        assert browser.put(endpoint, headers=learner, json={"title": "Private"}).status_code in (200, 204)
        assert "Private" in browser.get("/api/libraries", headers=learner).text
        assert "Private" not in browser.get("/api/libraries").text
        assert browser.post("/api/account/register", json=credentials, headers=HEADERS).status_code == 409
        assert browser.get("/api/account/session").json() == {"username": username}
        assert browser.post("/api/account/login", json=other, headers=HEADERS).status_code == 200
        assert browser.get("/api/libraries", headers=learner).status_code == 401
        other_headers = {**HEADERS, "X-Zhixue-Learner": other["username"]}
        assert "Private" not in browser.get("/api/libraries", headers=other_headers).text


def test_origin_and_custom_header_required_and_validation_redacted(tmp_path):
    with browser_at(tmp_path) as browser:
        for headers in ({}, {"Origin": ORIGIN}, {"Origin": "https://elsewhere.test", "X-Zhixue-Account": "1"}):
            assert browser.post("/api/account/login", headers=headers, json={}).status_code == 403
        for endpoint, method in (("/logout", "POST"), ("/materials/id", "PUT"), ("/materials/id", "DELETE")):
            assert browser.request(method, "/api/account" + endpoint, headers={"Origin": ORIGIN}).status_code == 403
        response = browser.post("/api/account/login", headers=HEADERS,
                                json={"username": "bad", "password": "PRIVATE"})
        assert response.status_code == 422
        assert "PRIVATE" not in response.text
        assert response.headers["cache-control"] == "no-store"


def test_gateway_fails_closed_when_auth_service_unavailable(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("test unavailable")
    monkeypatch.setattr(account_web.requests, "post", unavailable)
    with browser_at(tmp_path) as browser:
        assert browser.get("/").status_code == 200
        assert browser.get("/api/libraries").status_code == 200
        browser.cookies.set(ACCOUNT_COOKIE, "b" * 43)
        assert browser.get("/api/account/materials").status_code == 503
        assert browser.post("/api/account/logout", headers=HEADERS).status_code == 503
        assert not (tmp_path / "data" / "account-spaces").exists()


def test_incorrect_bindings_cannot_open_an_existing_account_db(tmp_path, monkeypatch):
    space = tmp_path / "data" / "account-spaces" / ("a" * 48)
    owner = account_web.AccountIdentity("owner", "test_owner", space)
    with account_web.materials_db(owner) as db:
        db.execute("INSERT INTO account_materials VALUES ('secret', 'Title', 'private', 0)")
    other = account_web.AccountIdentity("other", "test_other", space)
    monkeypatch.setattr(account_web, "resolve_account", lambda *_: other)
    with browser_at(tmp_path) as browser:
        browser.cookies.set(ACCOUNT_COOKIE, "b" * 43)
        assert browser.get("/api/account/materials/secret").status_code == 503
        assert browser.delete("/api/account/materials/secret", headers=HEADERS).status_code == 503
    with account_web.materials_db(owner) as db:
        assert db.execute("SELECT text FROM account_materials").fetchone()[0] == "private"


def test_account_routes_disabled_by_default(tmp_path):
    with browser_at(tmp_path, enabled=False) as browser:
        assert browser.get("/account").status_code == 404
        assert browser.get("/api/account/session").status_code == 404
        assert browser.get("/").status_code == 200
        assert browser.get("/api/libraries").status_code == 200
