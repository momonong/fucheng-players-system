import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .database import create_db_engine, make_session_factory
from .models import (
    Admin,
    Competition,
    CompetitionAudit,
    CompetitionRegistration,
    LoginSession,
    Member,
    MemberAudit,
    RegistrationAudit,
    now_utc,
)
from .schemas import (
    AdminCompetition,
    AdminMember,
    AdminRegistration,
    AuditEntry,
    AuthResponse,
    CompetitionCreate,
    CompetitionDetail,
    CompetitionUpdate,
    LoginRequest,
    MemberCreate,
    MemberUpdate,
    PublicMember,
    RegistrationCreate,
    RegistrationDietUpdate,
    RegistrationLevelUpdate,
    RegistrationMember,
    RegistrationMutation,
)
from .registrations import (
    _as_utc, _member_values, _changes, _begin_immediate, _competition_values,
    _competition_response, _registration_response, _mutate_registration, create_registration_service,
)
from .security import new_token, token_hash, verify_password

SESSION_COOKIE = "fucheng_session"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    session_cookie = "fucheng_http_preview_session" if settings.local_http_preview else SESSION_COOKIE
    engine = create_db_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    app = FastAPI(title="府城球館會員管理系統", docs_url=None, redoc_url=None)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings
    if settings.public_origin:
        from .proxy import DeploymentBoundary
        app.add_middleware(DeploymentBoundary, settings=settings)
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request, _error):
        return JSONResponse(status_code=422, content={"detail": "輸入格式不正確，請檢查欄位內容"})

    @app.exception_handler(DBAPIError)
    async def database_error(_request, error):
        # Do not log SQL parameters containing credentials/hashes or serialize DB exceptions.
        return JSONResponse(status_code=409 if isinstance(error, IntegrityError) else 503,
            content={"detail": "資料已變更或服務忙碌，請重新載入後再試"})

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    async def get_db():
        with session_factory() as db:
            yield db

    Db = Annotated[Session, Depends(get_db)]

    def current_auth(
        db: Db,
        request: Request,
    ) -> tuple[Admin, LoginSession]:
        fucheng_session = request.cookies.get(session_cookie)
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
    def login(payload: LoginRequest, request: Request, response: Response, db: Db) -> AuthResponse:
        from .public_registration import rate_limit, DUMMY_HASH
        from sqlalchemy import delete
        rate_limit(db, request, "admin-login", payload.username.strip())
        db.execute(text("BEGIN IMMEDIATE"))
        admin = db.scalar(select(Admin).where(Admin.username == payload.username.strip()))
        valid = verify_password(payload.password, admin.password_hash if admin else DUMMY_HASH)
        if not admin or not admin.is_active or not valid:
            raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
        db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(request.cookies.get(session_cookie, ""))))
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
            session_cookie,
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
        response.delete_cookie(session_cookie, path="/")

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
        _begin_immediate(db, auth)
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

    @app.get("/api/admin/registration-members", response_model=list[RegistrationMember])
    def registration_members(
        db: Db,
        _auth: Auth,
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
        return list(db.scalars(statement.order_by(Member.level, Member.name, Member.id).limit(100)))

    @app.get("/api/admin/competitions", response_model=list[AdminCompetition])
    def list_competitions(db: Db, _auth: Auth, deleted: bool = False) -> list[AdminCompetition]:
        competitions = db.scalars(
            select(Competition).where(Competition.deleted_at.is_not(None) if deleted else Competition.deleted_at.is_(None)).order_by(Competition.competition_date.desc(), Competition.created_at.desc())
        )
        return [_competition_response(db, competition) for competition in competitions]

    @app.post("/api/admin/competitions", response_model=AdminCompetition, status_code=201)
    def create_competition(payload: CompetitionCreate, db: Db, auth: CsrfAuth) -> AdminCompetition:
        admin_id = _begin_immediate(db, auth)
        if payload.status not in {"draft", "open"}:
            db.rollback()
            raise HTTPException(status_code=422, detail="新比賽只能建立為草稿或報名中")
        values = payload.model_dump()
        competition = Competition(**values, created_at=now_utc(), updated_at=now_utc())
        db.add(competition)
        db.flush()
        db.add(CompetitionAudit(
            competition_id=competition.id,
            admin_id=admin_id,
            action="create",
            changes_json=json.dumps(_changes({}, _competition_values(competition)), ensure_ascii=False, default=str),
        ))
        db.commit()
        return _competition_response(db, competition)

    @app.get("/api/admin/competitions/{competition_id}", response_model=CompetitionDetail)
    def get_competition(competition_id: str, db: Db, _auth: Auth) -> CompetitionDetail:
        competition = db.get(Competition, competition_id)
        if not competition:
            raise HTTPException(status_code=404, detail="找不到比賽")
        registrations = db.scalars(
            select(CompetitionRegistration)
            .where(CompetitionRegistration.competition_id == competition_id)
            .order_by(CompetitionRegistration.queue_sequence, CompetitionRegistration.id)
        )
        return CompetitionDetail(
            competition=_competition_response(db, competition),
            registrations=[_registration_response(item) for item in registrations],
        )

    @app.put("/api/admin/competitions/{competition_id}", response_model=AdminCompetition)
    def update_competition(
        competition_id: str,
        payload: CompetitionUpdate,
        db: Db,
        auth: CsrfAuth,
    ) -> AdminCompetition:
        admin_id = _begin_immediate(db, auth)
        competition = db.get(Competition, competition_id)
        if not competition:
            db.rollback()
            raise HTTPException(status_code=404, detail="找不到比賽")
        if competition.deleted_at:
            db.rollback()
            raise HTTPException(409, "比賽已刪除，請先還原")
        if competition.status in {"ended", "cancelled"}:
            db.rollback()
            raise HTTPException(status_code=409, detail="已結束或已取消的比賽為唯讀")
        if competition.version != payload.version:
            db.rollback()
            raise HTTPException(status_code=409, detail="此比賽已被其他管理員更新，請重新載入")
        allowed = {
            "draft": {"draft", "open", "cancelled"},
            "open": {"open", "closed", "cancelled"},
            "closed": {"closed", "ended", "cancelled"},
        }
        if payload.status not in allowed[competition.status]:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"不可從「{competition.status}」直接轉為「{payload.status}」",
            )
        confirmed = db.scalar(
            select(func.count(CompetitionRegistration.id)).where(
                CompetitionRegistration.competition_id == competition_id,
                CompetitionRegistration.status == "confirmed",
            )
        ) or 0
        if payload.capacity < confirmed:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"名額不可低於目前 {confirmed} 位正取")
        before = _competition_values(competition)
        after = payload.model_dump(exclude={"version", "reason"})
        changes = _changes(before, after)
        if not changes:
            db.rollback()
            return _competition_response(db, competition)
        result = db.execute(
            update(Competition)
            .where(Competition.id == competition_id, Competition.version == payload.version)
            .values(**after, version=Competition.version + 1, updated_at=now_utc())
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="此比賽已被其他管理員更新，請重新載入")
        db.add(CompetitionAudit(
            competition_id=competition_id,
            admin_id=admin_id,
            action="update",
            changes_json=json.dumps(changes, ensure_ascii=False, default=str),
            reason=payload.reason,
        ))
        db.commit()
        return _competition_response(db, db.get(Competition, competition_id))

    @app.post(
        "/api/admin/competitions/{competition_id}/registrations",
        response_model=AdminRegistration,
        status_code=201,
    )
    def create_registration(
        competition_id: str,
        payload: RegistrationCreate,
        db: Db,
        auth: CsrfAuth,
    ) -> AdminRegistration:
        return create_registration_service(db, auth, competition_id, payload)

    @app.post("/api/admin/registrations/{registration_id}/cancel", response_model=AdminRegistration)
    def cancel_registration(
        registration_id: str,
        payload: RegistrationMutation,
        db: Db,
        auth: CsrfAuth,
    ) -> AdminRegistration:
        return _mutate_registration(db, auth, registration_id, payload, "cancel")

    @app.post("/api/admin/registrations/{registration_id}/promote", response_model=AdminRegistration)
    def promote_registration(
        registration_id: str,
        payload: RegistrationMutation,
        db: Db,
        auth: CsrfAuth,
    ) -> AdminRegistration:
        return _mutate_registration(db, auth, registration_id, payload, "promote")

    @app.put("/api/admin/registrations/{registration_id}/diet", response_model=AdminRegistration)
    def update_registration_diet(
        registration_id: str,
        payload: RegistrationDietUpdate,
        db: Db,
        auth: CsrfAuth,
    ) -> AdminRegistration:
        return _mutate_registration(db, auth, registration_id, payload, "diet")

    @app.put("/api/admin/registrations/{registration_id}/level", response_model=AdminRegistration)
    def update_registration_level(registration_id: str, payload: RegistrationLevelUpdate, db: Db, auth: CsrfAuth):
        return _mutate_registration(db, auth, registration_id, payload, "level")

    from .public_registration import install_public_routes
    install_public_routes(app, get_db, current_auth)

    from .website import install_website_routes
    install_website_routes(app, get_db, current_auth, require_csrf)

    from .competition_deletion import install_competition_deletion_routes
    install_competition_deletion_routes(app, get_db, require_csrf)

    from .roster_import import install_roster_import_route
    install_roster_import_route(app, get_db, require_csrf)

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


app = create_app()
