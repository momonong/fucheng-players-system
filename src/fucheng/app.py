import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
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
    RegistrationMember,
    RegistrationMutation,
)
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
    def list_competitions(db: Db, _auth: Auth) -> list[AdminCompetition]:
        competitions = db.scalars(
            select(Competition).order_by(Competition.competition_date.desc(), Competition.created_at.desc())
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
        admin_id = _begin_immediate(db, auth)
        duplicate = _idempotent_registration(db, payload.request_id, "create", competition_id)
        if duplicate:
            db.rollback()
            return _registration_response(duplicate)
        competition = _mutable_competition(db, competition_id)
        if competition.status == "draft":
            db.rollback()
            raise HTTPException(status_code=409, detail="草稿比賽不接受報名")
        _require_late_reason(competition, payload.reason)
        member = db.get(Member, payload.member_id)
        if not member or not member.is_active:
            db.rollback()
            raise HTTPException(status_code=409, detail="只能選取啟用中的會員")
        existing = db.scalar(select(CompetitionRegistration).where(
            CompetitionRegistration.competition_id == competition_id,
            CompetitionRegistration.member_id == member.id,
            CompetitionRegistration.status != "cancelled",
        ))
        if existing:
            db.rollback()
            raise HTTPException(status_code=409, detail="此會員已有目前報名紀錄")
        confirmed = db.scalar(select(func.count(CompetitionRegistration.id)).where(
            CompetitionRegistration.competition_id == competition_id,
            CompetitionRegistration.status == "confirmed",
        )) or 0
        waiting = db.scalar(select(func.count(CompetitionRegistration.id)).where(
            CompetitionRegistration.competition_id == competition_id,
            CompetitionRegistration.status == "waitlisted",
        )) or 0
        registration = CompetitionRegistration(
            competition_id=competition_id,
            member_id=member.id,
            status="confirmed" if confirmed < competition.capacity and waiting == 0 else "waitlisted",
            diet=payload.diet or member.diet,
            hard_level_snapshot=member.level,
            queue_sequence=competition.next_sequence,
            created_by_admin_id=admin_id,
            updated_by_admin_id=admin_id,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        competition.next_sequence += 1
        db.add(registration)
        try:
            db.flush()
            db.add(_registration_audit(
                registration,
                admin_id,
                "create",
                {"status": {"before": None, "after": registration.status}},
                payload.reason,
                payload.request_id,
            ))
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(status_code=409, detail="報名已存在或同一操作已完成") from error
        return _registration_response(registration)

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


def _begin_immediate(db: Session, auth: tuple[Admin, LoginSession]) -> str:
    """驗證依賴已做過唯讀查詢；先結束該交易，再以 SQLite 寫鎖開始關鍵區段。"""
    admin_id = auth[0].id
    db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))
    return admin_id


def _competition_values(competition: Competition) -> dict[str, object]:
    return {
        "name": competition.name,
        "competition_date": competition.competition_date,
        "capacity": competition.capacity,
        "registration_deadline": competition.registration_deadline,
        "notes": competition.notes,
        "status": competition.status,
    }


def _competition_response(db: Session, competition: Competition) -> AdminCompetition:
    rows = db.execute(
        select(
            CompetitionRegistration.status,
            CompetitionRegistration.diet,
            CompetitionRegistration.hard_level_snapshot,
            func.count(CompetitionRegistration.id),
        )
        .where(CompetitionRegistration.competition_id == competition.id)
        .group_by(
            CompetitionRegistration.status,
            CompetitionRegistration.diet,
            CompetitionRegistration.hard_level_snapshot,
        )
    ).all()
    status_counts = {"confirmed": 0, "waitlisted": 0, "cancelled": 0}
    diet_counts = {"unset": 0, "omnivore": 0, "vegetarian": 0}
    level_counts: dict[int, int] = {}
    for registration_status, diet, level, count in rows:
        status_counts[registration_status] += count
        if registration_status == "confirmed":
            diet_counts[diet] += count
            level_counts[level] = level_counts.get(level, 0) + count
    remaining = max(competition.capacity - status_counts["confirmed"], 0)
    return AdminCompetition(
        **_competition_values(competition),
        id=competition.id,
        version=competition.version,
        created_at=competition.created_at,
        updated_at=competition.updated_at,
        effective_registration_open=(
            competition.status == "open" and now_utc() < _as_utc(competition.registration_deadline)
        ),
        summary={
            **status_counts,
            "remaining": remaining,
            "pending_promotions": min(remaining, status_counts["waitlisted"]),
            "diet_counts": diet_counts,
            "level_counts": level_counts,
        },
    )


def _registration_response(registration: CompetitionRegistration) -> AdminRegistration:
    return AdminRegistration(
        id=registration.id,
        competition_id=registration.competition_id,
        member_id=registration.member_id,
        member_name=registration.member.name,
        distinguishing_note=registration.member.distinguishing_note,
        status=registration.status,
        diet=registration.diet,
        hard_level_snapshot=registration.hard_level_snapshot,
        queue_sequence=registration.queue_sequence,
        version=registration.version,
        created_by_username=registration.created_by.username,
        updated_by_username=registration.updated_by.username,
        created_at=registration.created_at,
        updated_at=registration.updated_at,
    )


def _mutable_competition(db: Session, competition_id: str) -> Competition:
    competition = db.get(Competition, competition_id)
    if not competition:
        db.rollback()
        raise HTTPException(status_code=404, detail="找不到比賽")
    if competition.status in {"ended", "cancelled"}:
        db.rollback()
        raise HTTPException(status_code=409, detail="已結束或已取消的比賽為唯讀")
    return competition


def _require_late_reason(competition: Competition, reason: str | None) -> None:
    late = competition.status == "closed" or now_utc() >= _as_utc(competition.registration_deadline)
    if late and not (reason and reason.strip()):
        raise HTTPException(status_code=422, detail="報名截止後的操作必須填寫原因")


def _idempotent_registration(
    db: Session,
    request_id: str,
    action: str,
    competition_id: str | None = None,
) -> CompetitionRegistration | None:
    audit = db.scalar(select(RegistrationAudit).where(RegistrationAudit.idempotency_key == request_id))
    if not audit:
        return None
    if audit.action != action or (competition_id and audit.competition_id != competition_id):
        raise HTTPException(status_code=409, detail="此操作識別碼已用於其他操作")
    return db.get(CompetitionRegistration, audit.registration_id)


def _registration_audit(
    registration: CompetitionRegistration,
    admin_id: str,
    action: str,
    changes: dict[str, dict[str, object]],
    reason: str | None,
    request_id: str,
) -> RegistrationAudit:
    return RegistrationAudit(
        registration_id=registration.id,
        competition_id=registration.competition_id,
        admin_id=admin_id,
        action=action,
        changes_json=json.dumps(changes, ensure_ascii=False),
        reason=reason.strip() if reason else None,
        idempotency_key=request_id,
    )


def _mutate_registration(
    db: Session,
    auth: tuple[Admin, LoginSession],
    registration_id: str,
    payload: RegistrationMutation | RegistrationDietUpdate,
    action: str,
) -> AdminRegistration:
    admin_id = _begin_immediate(db, auth)
    duplicate = _idempotent_registration(db, payload.request_id, action)
    if duplicate:
        db.rollback()
        return _registration_response(duplicate)
    registration = db.get(CompetitionRegistration, registration_id)
    if not registration:
        db.rollback()
        raise HTTPException(status_code=404, detail="找不到報名紀錄")
    competition = _mutable_competition(db, registration.competition_id)
    if registration.version != payload.version:
        db.rollback()
        raise HTTPException(status_code=409, detail="此報名已被其他管理員更新，請重新載入")
    before = {"status": registration.status, "diet": registration.diet}
    if action == "cancel":
        if registration.status == "cancelled":
            db.rollback()
            raise HTTPException(status_code=409, detail="此報名已取消")
        _require_late_reason(competition, payload.reason)
        registration.status = "cancelled"
    elif action == "promote":
        if registration.status != "waitlisted":
            db.rollback()
            raise HTTPException(status_code=409, detail="只有有效候補可以遞補")
        _require_late_reason(competition, payload.reason)
        first_waiting = db.scalar(
            select(CompetitionRegistration)
            .where(
                CompetitionRegistration.competition_id == competition.id,
                CompetitionRegistration.status == "waitlisted",
            )
            .order_by(CompetitionRegistration.queue_sequence, CompetitionRegistration.id)
            .limit(1)
        )
        if not first_waiting or first_waiting.id != registration.id:
            db.rollback()
            raise HTTPException(status_code=409, detail="只能先處理第一位有效候補")
        confirmed = db.scalar(select(func.count(CompetitionRegistration.id)).where(
            CompetitionRegistration.competition_id == competition.id,
            CompetitionRegistration.status == "confirmed",
        )) or 0
        if confirmed >= competition.capacity:
            db.rollback()
            raise HTTPException(status_code=409, detail="目前沒有可遞補名額")
        registration.status = "confirmed"
    elif action == "diet":
        if registration.status == "cancelled":
            db.rollback()
            raise HTTPException(status_code=409, detail="已取消報名為歷史紀錄，不可修改")
        _require_late_reason(competition, payload.reason)
        registration.diet = payload.diet
    else:
        db.rollback()
        raise RuntimeError("未知報名操作")
    registration.version += 1
    registration.updated_by_admin_id = admin_id
    registration.updated_at = now_utc()
    after = {"status": registration.status, "diet": registration.diet}
    changes = _changes(before, after)
    db.add(_registration_audit(
        registration,
        admin_id,
        action,
        changes,
        payload.reason,
        payload.request_id,
    ))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="此操作已完成或資料已變更") from error
    return _registration_response(registration)


app = create_app()
