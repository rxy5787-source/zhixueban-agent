"""Same-origin gateway for account sessions and the first protected materials API."""

from contextlib import closing, contextmanager
from pathlib import Path
import re
import sqlite3
import time
from uuid import uuid4

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from . import config
from .account_space import AccountIdentity, resolve_account

TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
MAX_MATERIALS = 100


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(pattern=r"^[A-Za-z0-9_]{4,32}$")
    password: SecretStr = Field(min_length=8, max_length=128)


class Material(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=20000)


def auth_request(action, **options):
    try:
        result = requests.post(f"{config.AUTH_URL}/api/auth/{action}",
                               timeout=(3, 5), allow_redirects=False, **options)
    except requests.RequestException:
        raise HTTPException(503, "账号服务暂不可用，请稍后重试") from None
    if result.status_code == 401:
        raise HTTPException(401, "账号或密码错误")
    if result.status_code == 429:
        raise HTTPException(429, "登录尝试过多，请稍后重试")
    if action == "register" and result.status_code == 409:
        raise HTTPException(409, "该用户名不可用，请换一个")
    if result.status_code != 200:
        raise HTTPException(503, "账号服务暂不可用，请稍后重试")
    return result


@contextmanager
def materials_db(identity: AccountIdentity):
    try:
        if identity.path.resolve() != identity.path:
            raise HTTPException(503, "账号学习空间暂不可用")
        identity.path.mkdir(parents=True, exist_ok=True)
        path = identity.path / "materials.sqlite3"
        if path.resolve() != path:
            raise HTTPException(503, "账号学习空间暂不可用")
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS space_owner (id INTEGER PRIMARY KEY CHECK(id=1), user_id TEXT NOT NULL)")
            owner = db.execute("SELECT user_id FROM space_owner WHERE id=1").fetchone()
            if owner is None:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name!='space_owner'").fetchone():
                    raise HTTPException(503, "账号学习空间暂不可用")
                db.execute("INSERT INTO space_owner VALUES (1, ?)", (identity.user_id,))
            elif owner["user_id"] != identity.user_id:
                raise HTTPException(503, "账号学习空间暂不可用")
            db.execute("""CREATE TABLE IF NOT EXISTS account_materials (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, text TEXT NOT NULL, updated REAL NOT NULL
            )""")
            yield db
    except (OSError, RuntimeError, sqlite3.Error):
        raise HTTPException(503, "账号学习空间暂不可用") from None


def material_by_id(db, material_id):
    material = db.execute("SELECT id,title,text,updated FROM account_materials WHERE id=?", (material_id,)).fetchone()
    if material is None:
        raise HTTPException(404, "资料不存在")
    return dict(material)


def account_cookie(secure: bool) -> str:
    return "__Host-zhixue-account" if secure else "zhixue-account-dev"


def account_authorization(request: Request, secure: bool) -> str:
    token = request.cookies.get(account_cookie(secure), "")
    if not TOKEN.fullmatch(token):
        raise HTTPException(401, "请先登录")
    return f"Bearer {token}"


def account_routes(data_root: Path, *, secure: bool):
    router = APIRouter(prefix="/api/account")
    cookie = account_cookie(secure)
    cookie_options = dict(httponly=True, secure=secure, samesite="lax", path="/")

    def identity(request: Request) -> AccountIdentity:
        account = resolve_account(account_authorization(request, secure), data_root)
        expected = request.headers.get("x-zhixue-learner")
        if expected is not None and expected != account.username:
            raise HTTPException(401, "账号已切换，请重新进入学习空间")
        return account

    def sign_in(action: str, credentials: Credentials, request: Request, response: Response):
        result = auth_request(action, json={
            "username": credentials.username, "password": credentials.password.get_secret_value(),
        })
        try:
            payload = result.json()
            token = payload["token"]
            remaining = int(payload["expiresAt"] / 1000 - time.time())
            if not TOKEN.fullmatch(token) or not 0 < remaining <= 2592000:
                raise ValueError("invalid session")
            account = resolve_account(f"Bearer {token}", data_root)
        except (KeyError, TypeError, ValueError, OverflowError):
            raise HTTPException(503, "账号服务暂不可用，请稍后重试") from None
        previous = request.cookies.get(cookie, "")
        if TOKEN.fullmatch(previous):
            auth_request("logout", headers={"Authorization": f"Bearer {previous}"})
        response.set_cookie(cookie, token, max_age=remaining, **cookie_options)
        return {"username": account.username}

    @router.post("/login")
    def login(credentials: Credentials, request: Request, response: Response):
        return sign_in("login", credentials, request, response)

    @router.post("/register", status_code=201)
    def register(credentials: Credentials, request: Request, response: Response):
        if len(credentials.password.get_secret_value()) < 15:
            raise HTTPException(422, "新密码至少需要 15 个字符")
        return sign_in("register", credentials, request, response)

    @router.get("/session")
    def session(account: AccountIdentity = Depends(identity)):
        return {"username": account.username}

    @router.post("/logout", status_code=204)
    def logout(request: Request):
        token = request.cookies.get(cookie, "")
        if TOKEN.fullmatch(token):
            auth_request("logout", headers={"Authorization": f"Bearer {token}"})
        response = Response(status_code=204)
        response.delete_cookie(cookie, **cookie_options)
        return response

    @router.get("/materials")
    def list_materials(account: AccountIdentity = Depends(identity)):
        with materials_db(account) as db:
            return [dict(row) for row in db.execute("SELECT id,title,updated FROM account_materials ORDER BY updated DESC,id")]

    @router.post("/materials", status_code=201)
    def create_material(material: Material, account: AccountIdentity = Depends(identity)):
        with materials_db(account) as db:
            if db.execute("SELECT COUNT(*) FROM account_materials").fetchone()[0] >= MAX_MATERIALS:
                raise HTTPException(409, "此学习空间已达到资料数量上限")
            material_id = uuid4().hex
            db.execute("INSERT INTO account_materials VALUES (?,?,?,?)",
                       (material_id, material.title, material.text, time.time()))
            return material_by_id(db, material_id)

    @router.get("/materials/{material_id}")
    def read_material(material_id: str, account: AccountIdentity = Depends(identity)):
        with materials_db(account) as db:
            return material_by_id(db, material_id)

    @router.put("/materials/{material_id}")
    def update_material(material_id: str, material: Material, account: AccountIdentity = Depends(identity)):
        with materials_db(account) as db:
            if not db.execute("UPDATE account_materials SET title=?,text=?,updated=? WHERE id=?",
                              (material.title, material.text, time.time(), material_id)).rowcount:
                raise HTTPException(404, "资料不存在")
            return material_by_id(db, material_id)

    @router.delete("/materials/{material_id}", status_code=204)
    def delete_material(material_id: str, account: AccountIdentity = Depends(identity)):
        with materials_db(account) as db:
            if not db.execute("DELETE FROM account_materials WHERE id=?", (material_id,)).rowcount:
                raise HTTPException(404, "资料不存在")
        return Response(status_code=204)

    return router
