"""Administrator account lifecycle; credentials never enter audit payloads."""
import json
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased

from .models import Admin, AdminAudit, LoginSession, now_utc
from .registrations import _begin_immediate
from .security import hash_password, verify_password


class Account(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    display_name: str | None
    is_active: bool
    must_change_password: bool
    version: int
    created_at: datetime
    updated_at: datetime


def normalize_username(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 80 or not value.isprintable():
        raise ValueError("帳號須為 1–80 個可顯示字元")
    return value


def normalize_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 100 or not value.isprintable():
        raise ValueError("姓名須為 100 字以內的可顯示文字")
    return value


class NewAccount(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    display_name: str | None = Field(default=None, max_length=100)
    password: str = Field(min_length=12, max_length=256, repr=False)
    current_password: str = Field(min_length=1, max_length=256, repr=False)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value):
        return normalize_username(value)

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value):
        return normalize_display_name(value)


class PasswordChange(BaseModel):
    version: int = Field(ge=1)
    current_password: str = Field(min_length=1, max_length=256, repr=False)
    password: str = Field(min_length=12, max_length=256, repr=False)


class StatusChange(BaseModel):
    version: int = Field(ge=1)
    is_active: bool
    current_password: str = Field(min_length=1, max_length=256, repr=False)


class AccountAudit(BaseModel):
    id: str
    actor_admin_id: str | None
    actor_username: str | None
    actor_display_name: str | None
    target_admin_id: str
    target_username: str
    target_display_name: str | None
    action: str
    source: str
    changes: dict[str, dict[str, object]]
    created_at: datetime


def audit_account(db, target, action, *, actor_id=None, source="web", changes=None):
    db.add(AdminAudit(actor_admin_id=actor_id, target_admin_id=target.id,
        action=action, source=source, changes_json=json.dumps(changes or {}, ensure_ascii=False)))


def create_account(db, username, password, *, display_name=None, actor_id=None, source="cli", must_change_password=True):
    """Caller owns the write transaction and commit, including the audit row."""
    username = normalize_username(username)
    display_name = normalize_display_name(display_name)
    if len(password) > 256:
        raise ValueError("密碼至多 256 個字元")
    if db.scalar(select(Admin.id).where(Admin.username == username)):
        raise HTTPException(409, "此管理員帳號已存在")
    target = Admin(username=username, display_name=display_name, password_hash=hash_password(password),
        must_change_password=must_change_password, updated_at=now_utc())
    db.add(target)
    db.flush()
    audit_account(db, target, "bootstrap" if source == "bootstrap" else "create", actor_id=actor_id,
        source=source, changes={"username": {"before": None, "after": username},
            "display_name": {"before": None, "after": display_name},
            "is_active": {"before": None, "after": True},
            "must_change_password": {"before": None, "after": must_change_password}})
    return target


def bootstrap_first_admin(session_factory, username: str | None, password_file: str | Path | None, display_name: str | None = None):
    """First serve only. An existing account (even inactive) disables bootstrap."""
    with session_factory() as db:
        try:
            return _bootstrap_first_admin(db, username, password_file, display_name)
        except DBAPIError:
            # A failed commit can leave SQLAlchemy's transaction inactive while
            # SQLite still holds uncommitted data. Close the physical connection
            # before it can return to the pool; never print bound credentials.
            db.invalidate()
            raise RuntimeError("首位管理員建立失敗；請檢查資料庫狀態後重試") from None


def _bootstrap_first_admin(db, username, password_file, display_name):
    db.execute(text("BEGIN IMMEDIATE"))
    if db.scalar(select(Admin.id).limit(1)):
        return None
    if not username or not password_file:
        raise RuntimeError("資料庫沒有管理員；請設定首位管理員帳號及受保護的密碼檔，或使用維護命令建立帳號")
    try:
        username = normalize_username(username)
        # O_NOFOLLOW prevents a swapped symlink from redirecting secret reads.
        fd = os.open(password_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as secret:
            info = os.fstat(secret.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) not in {0o400, 0o600}:
                raise ValueError("password file must be a private regular file")
            raw = secret.read(2049)
        if len(raw) > 2048:
            raise ValueError("password file too large")
        password = raw.decode("utf-8")
        if password.endswith("\r\n"):
            password = password[:-2]
        elif password.endswith("\n"):
            password = password[:-1]
        if "\n" in password or "\r" in password:
            raise ValueError("password file must contain one line")
        target = create_account(db, username, password, display_name=display_name, source="bootstrap", must_change_password=False)
    except (OSError, UnicodeError, ValueError):
        raise RuntimeError("首位管理員設定無效；姓名至多 100 字、帳號須為 1–80 字，密碼檔須可讀、權限 0400/0600，內含 12–256 字元單行密碼") from None
    db.commit()
    return target.id


def install_admin_management_routes(app, get_db, current_auth, require_csrf, session_cookie):
    Db = Annotated[Session, Depends(get_db)]
    Auth = Annotated[tuple, Depends(current_auth)]
    Write = Annotated[tuple, Depends(require_csrf)]

    def sensitive_actor(db, request, auth, password, *, allow_password_change=False):
        from .public_registration import rate_limit
        snapshot = (auth[1].id, auth[0].id, auth[0].version)
        actor_id = snapshot[1]
        rate_limit(db, request, "admin-sensitive", actor_id, identity_limit=15, ip_limit=60, global_limit=300)
        _begin_immediate(db, auth, allow_password_change=allow_password_change, auth_snapshot=snapshot)
        actor = db.get(Admin, actor_id)
        if not verify_password(password, actor.password_hash):
            raise HTTPException(403, "目前密碼不正確")
        return actor

    def target_account(db, target_id, version):
        target = db.get(Admin, target_id)
        if not target:
            raise HTTPException(404, "找不到管理員")
        if target.version != version:
            raise HTTPException(409, "此管理員資料已更新，請重新載入後再操作")
        return target

    @app.get("/api/admin/admins", response_model=list[Account])
    def accounts(db: Db, _auth: Auth):
        return list(db.scalars(select(Admin).order_by(Admin.is_active.desc(), Admin.username, Admin.id)))

    @app.post("/api/admin/admins", response_model=Account, status_code=201)
    def add_account(payload: NewAccount, request: Request, db: Db, auth: Write):
        actor = sensitive_actor(db, request, auth, payload.current_password)
        target = create_account(db, payload.username, payload.password, display_name=payload.display_name, actor_id=actor.id, source="web")
        db.commit()
        return target

    @app.put("/api/admin/admins/{target_id}/status", response_model=Account)
    def set_status(target_id: str, payload: StatusChange, request: Request, db: Db, auth: Write):
        actor = sensitive_actor(db, request, auth, payload.current_password)
        target = target_account(db, target_id, payload.version)
        if not payload.is_active:
            if target.id == actor.id:
                raise HTTPException(409, "不能停用自己的管理員帳號")
            count = db.scalar(select(func.count()).select_from(Admin).where(Admin.is_active.is_(True)))
            if target.is_active and count <= 1:
                raise HTTPException(409, "至少須保留一位啟用管理員")
        if target.is_active != payload.is_active:
            before = target.is_active
            target.is_active = payload.is_active
            target.version += 1
            target.updated_at = now_utc()
            db.execute(delete(LoginSession).where(LoginSession.admin_id == target.id))
            audit_account(db, target, "enable" if target.is_active else "disable", actor_id=actor.id,
                changes={"is_active": {"before": before, "after": target.is_active}})
        db.commit()
        return target

    def change_password(db, target, password, actor, *, reset):
        if verify_password(password, target.password_hash):
            raise HTTPException(422, "新密碼不可與目前密碼相同")
        before = target.must_change_password
        target.password_hash = hash_password(password)
        target.must_change_password = reset
        target.version += 1
        target.updated_at = now_utc()
        db.execute(delete(LoginSession).where(LoginSession.admin_id == target.id))
        audit_account(db, target, "reset_password" if reset else "change_password", actor_id=actor.id,
            changes={"must_change_password": {"before": before, "after": reset}})
        db.commit()

    @app.post("/api/admin/admins/{target_id}/reset-password", response_model=Account)
    def reset_password(target_id: str, payload: PasswordChange, request: Request, db: Db, auth: Write):
        actor = sensitive_actor(db, request, auth, payload.current_password)
        if actor.id == target_id:
            raise HTTPException(422, "請使用變更本人密碼功能")
        target = target_account(db, target_id, payload.version)
        change_password(db, target, payload.password, actor, reset=True)
        return target

    @app.post("/api/auth/change-password", status_code=204)
    def own_password(payload: PasswordChange, request: Request, response: Response, db: Db, auth: Write):
        actor = sensitive_actor(db, request, auth, payload.current_password, allow_password_change=True)
        target_account(db, actor.id, payload.version)
        change_password(db, actor, payload.password, actor, reset=False)
        response.delete_cookie(session_cookie, path=app.state.settings.base_path + "/")

    @app.get("/api/admin/admin-audits", response_model=list[AccountAudit])
    def audits(db: Db, _auth: Auth, limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000)):
        actor, target = aliased(Admin), aliased(Admin)
        rows = db.execute(select(AdminAudit, actor.username, actor.display_name, target.username, target.display_name)
            .outerjoin(actor, AdminAudit.actor_admin_id == actor.id)
            .join(target, AdminAudit.target_admin_id == target.id)
            .order_by(AdminAudit.created_at.desc(), AdminAudit.id).limit(limit).offset(offset))
        return [AccountAudit(id=row.id, actor_admin_id=row.actor_admin_id, actor_username=actor_name, actor_display_name=actor_display,
            target_admin_id=row.target_admin_id, target_username=target_name, target_display_name=target_display, action=row.action,
            source=row.source, changes=json.loads(row.changes_json), created_at=row.created_at)
            for row, actor_name, actor_display, target_name, target_display in rows]
