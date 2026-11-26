from unittest.mock import Mock

import pytest
import requests
from fastapi import HTTPException

from backend import account_space
from backend.job_store import Store

TOKEN_A = "Bearer " + "A" * 43
TOKEN_B = "Bearer " + "B" * 43
SPACE_A = "a" * 48
SPACE_B = "b" * 48


def test_account_resolution_uses_separate_namespace_and_storage(monkeypatch, tmp_path):
    sessions = {TOKEN_A: SPACE_A, TOKEN_B: SPACE_B}

    def resolve(url, *, headers, timeout, allow_redirects):
        assert url.endswith("/api/auth/learning-space")
        assert set(headers) == {"Authorization"}
        assert timeout == (3, 5)
        assert not allow_redirects
        return Mock(status_code=200, **{"json.return_value": {
            "spaceId": sessions[headers["Authorization"]],
            "user": {"id": "a" * 36, "username": "test_user"},
        }})

    monkeypatch.setattr(account_space.requests, "post", resolve)
    guest = Store(tmp_path / "spaces" / SPACE_A)
    first_path = account_space.resolve_account_space(TOKEN_A, tmp_path)
    assert first_path == account_space.resolve_account_space(TOKEN_A, tmp_path)
    second_path = account_space.resolve_account_space(TOKEN_B, tmp_path)
    assert first_path == tmp_path / "account-spaces" / SPACE_A
    assert second_path == tmp_path / "account-spaces" / SPACE_B
    assert not first_path.exists()
    assert not second_path.exists()

    first, second = Store(first_path), Store(second_path)
    with first.db() as db:
        db.execute("INSERT INTO settings(key,value) VALUES (?,?)", ("test-private-marker", "account-a"))
    for store in (second, guest):
        with store.db() as db:
            assert db.execute("SELECT value FROM settings WHERE key=?", ("test-private-marker",)).fetchone() is None


@pytest.mark.parametrize("authorization", [None, "guest-cookie", "Bearer short"])
def test_unverified_identity_does_not_resolve(monkeypatch, tmp_path, authorization):
    post = Mock()
    monkeypatch.setattr(account_space.requests, "post", post)
    with pytest.raises(HTTPException) as error:
        account_space.resolve_account_space(authorization, tmp_path)
    assert error.value.status_code == 401
    post.assert_not_called()


@pytest.mark.parametrize("status, payload, expected", [
    (401, {}, 401),
    (302, {"spaceId": SPACE_A}, 503),
    (500, {}, 503),
    (200, {"spaceId": "../spaces/visitor"}, 503),
    (200, [], 503),
])
def test_bad_auth_response_fails_closed(monkeypatch, tmp_path, status, payload, expected):
    post = Mock(return_value=Mock(status_code=status, **{"json.return_value": payload}))
    monkeypatch.setattr(account_space.requests, "post", post)
    with pytest.raises(HTTPException) as error:
        account_space.resolve_account_space(TOKEN_A, tmp_path)
    assert error.value.status_code == expected
    assert not (tmp_path / "account-spaces").exists()


def test_auth_service_timeout_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(account_space.requests, "post", Mock(side_effect=requests.Timeout))
    with pytest.raises(HTTPException) as error:
        account_space.resolve_account_space(TOKEN_A, tmp_path)
    assert error.value.status_code == 503
