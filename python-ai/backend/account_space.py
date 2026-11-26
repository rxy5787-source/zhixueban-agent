"""Server-side account-space resolution. Guest routes do not use this module."""

from pathlib import Path
import re

from typing import NamedTuple

import requests
from fastapi import HTTPException

from . import config


class AccountIdentity(NamedTuple):
    user_id: str
    username: str
    path: Path


def resolve_account(authorization: str | None, data_root: Path) -> AccountIdentity:
    """Resolve the identity and store from the same auth-server response."""
    if not authorization or not re.fullmatch(r"Bearer [A-Za-z0-9_-]{43}", authorization):
        raise HTTPException(401, "请先登录")

    try:
        response = requests.post(
            f"{config.AUTH_URL}/api/auth/learning-space",
            headers={"Authorization": authorization},
            timeout=(3, 5),
            allow_redirects=False,
        )
        if response.status_code == 401:
            raise HTTPException(401, "登录已失效，请重新登录")
        if response.status_code == 200:
            payload = response.json()
            space_id = payload.get("spaceId")
            user = payload.get("user", {})
            user_id = user.get("id")
            username = user.get("username")
            if isinstance(space_id, str) and re.fullmatch(r"[0-9a-f]{48}", space_id):
                path = data_root.resolve() / "account-spaces" / space_id
                if (isinstance(user_id, str) and re.fullmatch(r"[0-9a-f-]{36}", user_id)
                        and isinstance(username, str) and re.fullmatch(r"[A-Za-z0-9_]{4,32}", username)
                        and path.resolve() == path):
                    return AccountIdentity(user_id, username, path)
    except (requests.RequestException, ValueError, AttributeError, OSError, RuntimeError):
        pass
    raise HTTPException(503, "账号学习空间暂不可用，请稍后重试")


def resolve_account_space(authorization: str | None, data_root: Path) -> Path:
    return resolve_account(authorization, data_root).path
