import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .database import create_db_engine, make_session_factory
from .models import Admin, LoginSession, Member, MemberAudit, now_utc
from .schemas import AdminMember, AuditEntry, AuthResponse, LoginRequest, MemberCreate, MemberUpdate, PublicMember
from .security import new_token, token_hash, verify_password

SESSION_COOKIE = "fucheng_session"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = create_db_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    app = FastAPI(title="府城球館會員管理系統", docs_url=None, redoc_url=None)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings

    async def get_db():
        with session_factory() as db:
            yield db

    Db = Annotated[Session, Depends(get_db)]

    def current_auth(
        db: Db,
        fucheng_session: Annotated[str | None, Cookie()] = None,
    ) -> tuple[Admin, LoginSession]:
        if not fucheng_session:
            raise HTTPException(status_code=401, detail="請先登入")
        session = db.scalar(
            select(LoginSession).where(LoginSession.token_hash == token_hash(fucheng_session))
        )
        if not session or _as_utc(session.expires_at) <= now_utc() or not session.admin.is_active:
            if session:
                db.delete(session)
                db.commit()
            raise HTTPException(status_code=401, detail="登入已逾時，請重新登入")
        return session.admin, session

    Auth = Annotated[tuple[Admin, LoginSession], Depends(current_auth)]

    def require_csrf(
        auth: Auth,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> tuple[Admin, LoginSession]:
        if not x_csrf_token or x_csrf_token != auth[1].csrf_token:
            raise HTTPException(status_code=403, detail="安全驗證失敗，請重新整理後再試")
        return auth

    CsrfAuth = Annotated[tuple[Admin, LoginSession], Depends(require_csrf)]

    @app.get("/api/health")
    def health(db: Db) -> dict[str, str]:
        db.execute(select(1))
        return {"status": "ok"}

    @app.get("/api/public/members", response_model=list[PublicMember])
    def public_members(
        db: Db,
        search: str | None = Query(default=None, max_length=100),
        level: int | None = Query(default=None, ge=1, le=10),
    ) -> list[Member]:
        statement = select(Member).where(Member.is_active.is_(True))
        if search and search.strip():
            term = f"%{search.strip()}%"
            statement = statement.where(
                or_(Member.name.like(term), Member.distinguishing_note.like(term))
            )
        if level is not None:
            statement = statement.where(Member.level == level)
        return list(db.scalars(statement.order_by(Member.level.asc(), Member.name.asc(), Member.id.asc())))

    @app.post("/api/auth/login", response_model=AuthResponse)
    def login(payload: LoginRequest, response: Response, db: Db) -> AuthResponse:
        admin = db.scalar(select(Admin).where(Admin.username == payload.username.strip()))
        if not admin or not admin.is_active or not verify_password(payload.password, admin.password_hash):
            raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
        raw_token, csrf_token = new_token(), new_token()
        login_session = LoginSession(
            token_hash=token_hash(raw_token),
            csrf_token=csrf_token,
            admin_id=admin.id,
            expires_at=now_utc() + timedelta(hours=settings.session_hours),
        )
        db.add(login_session)
        db.commit()
        response.set_cookie(
            SESSION_COOKIE,
            raw_token,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            max_age=settings.session_hours * 3600,
            path="/",
        )
        return AuthResponse(username=admin.username, csrf_token=csrf_token)

    @app.get("/api/auth/me", response_model=AuthResponse)
    def me(auth: Auth) -> AuthResponse:
        return AuthResponse(username=auth[0].username, csrf_token=auth[1].csrf_token)

    @app.post("/api/auth/logout", status_code=204)
    def logout(response: Response, db: Db, auth: CsrfAuth) -> None:
        db.delete(auth[1])
        db.commit()
        response.delete_cookie(SESSION_COOKIE, path="/")

    @app.get("/api/admin/members", response_model=list[AdminMember])
    def admin_members(db: Db, _auth: Auth) -> list[Member]:
        return list(db.scalars(select(Member).order_by(Member.is_active.desc(), Member.level, Member.name)))

    @app.post("/api/admin/members", response_model=AdminMember, status_code=201)
    def create_member(payload: MemberCreate, db: Db, auth: CsrfAuth) -> Member:
        try:
            member = Member(**payload.model_dump(), created_at=now_utc(), updated_at=now_utc())
            db.add(member)
            db.flush()
            db.add(MemberAudit(
                member_id=member.id,
                admin_id=auth[0].id,
                action="create",
                changes_json=json.dumps(_changes({}, payload.model_dump()), ensure_ascii=False),
            ))
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(status_code=409, detail="會員編號已被使用") from error
        db.refresh(member)
        return member

    @app.put("/api/admin/members/{member_id}", response_model=AdminMember)
    def update_member(member_id: str, payload: MemberUpdate, db: Db, auth: CsrfAuth) -> Member:
        existing = db.get(Member, member_id)
        if not existing:
            raise HTTPException(status_code=404, detail="找不到會員")
        if existing.version != payload.version:
            raise HTTPException(status_code=409, detail="此會員已被其他管理員更新，請重新載入後再編輯")
        before = _member_values(existing)
        after = payload.model_dump(exclude={"version"})
        changes = _changes(before, after)
        if not changes:
            return existing
        updated_at = now_utc()
        result = db.execute(
            update(Member)
            .where(Member.id == member_id, Member.version == payload.version)
            .values(**after, version=Member.version + 1, updated_at=updated_at)
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="此會員已被其他管理員更新，請重新載入後再編輯")
        db.add(MemberAudit(
            member_id=member_id,
            admin_id=auth[0].id,
            action="update",
            changes_json=json.dumps(changes, ensure_ascii=False),
        ))
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(status_code=409, detail="會員編號已被使用") from error
        return db.get(Member, member_id)

    @app.get("/api/admin/members/{member_id}/history", response_model=list[AuditEntry])
    def member_history(member_id: str, db: Db, _auth: Auth) -> list[AuditEntry]:
        if not db.get(Member, member_id):
            raise HTTPException(status_code=404, detail="找不到會員")
        entries = db.scalars(
            select(MemberAudit).where(MemberAudit.member_id == member_id).order_by(MemberAudit.created_at.desc())
        )
        return [
            AuditEntry(
                id=entry.id,
                action=entry.action,
                changes=json.loads(entry.changes_json),
                admin_username=entry.admin.username,
                created_at=entry.created_at,
            )
            for entry in entries
        ]

    static_dir = settings.static_dir
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="找不到 API")
        index = static_dir / "index.html"
        if not index.exists():
            raise HTTPException(status_code=503, detail="前端尚未建置")
        candidate = (static_dir / path).resolve()
        if path and candidate.is_relative_to(static_dir.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return app


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _member_values(member: Member) -> dict[str, object]:
    return {
        "name": member.name,
        "distinguishing_note": member.distinguishing_note,
        "legacy_number": member.legacy_number,
        "level": member.level,
        "diet": member.diet,
        "is_active": member.is_active,
    }


def _changes(before: dict[str, object], after: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        key: {"before": before.get(key), "after": value}
        for key, value in after.items()
        if before.get(key) != value
    }


app = create_app()
