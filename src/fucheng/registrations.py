"""Shared registration rules. All mutations acquire the SQLite write lock before reading capacity."""
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .models import (Admin, LoginSession, Member, PublicVisit, Competition,
                     CompetitionRegistration, RegistrationAudit, now_utc)
from .schemas import AdminCompetition, AdminRegistration, RegistrationMutation, RegistrationDietUpdate
from .security import token_hash

@dataclass(frozen=True)
class Actor:
    kind: str
    admin_id: str | None = None
    visit_id: str | None = None


def actor_from_auth(auth):
    if isinstance(auth, PublicVisit):
        return Actor("public", visit_id=auth.id)
    return Actor("admin", admin_id=auth[0].id)


def actor_label(registration, prefix):
    kind = getattr(registration, prefix + "_kind")
    if kind == "admin":
        return "管理員：" + getattr(registration, prefix).username
    if kind == "public":
        return "免登入報名（身分未驗證）"
    return "系統"


def request_fingerprint(target, payload):
    return token_hash(json.dumps({"target": target, **payload.model_dump(exclude={"request_id"})}, sort_keys=True))


def require_member_open(competition):
    if competition.deleted_at or competition.status != "open" or now_utc() >= competition.registration_deadline:
        raise HTTPException(409, "此比賽目前不接受線上報名")


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


def _begin_immediate(db: Session, auth) -> str | None:
    """驗證依賴已做過唯讀查詢；先結束該交易，再以 SQLite 寫鎖開始關鍵區段。"""
    actor = actor_from_auth(auth)
    if actor.kind == "public":
        visit_id = auth.id
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
        visit = db.get(PublicVisit, visit_id)
        if not visit or visit.expires_at <= now_utc():
            raise HTTPException(401, "頁面已逾時，請重新整理後再試")
        return None
    session_id, admin_id = auth[1].id, auth[0].id
    db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))
    session = db.get(LoginSession, session_id)
    admin = db.get(Admin, admin_id)
    if not session or not admin or not admin.is_active or session.expires_at <= now_utc():
        raise HTTPException(401, "登入已逾時，請重新登入")
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
        deleted_at=competition.deleted_at,
        id=competition.id,
        version=competition.version,
        created_at=competition.created_at,
        updated_at=competition.updated_at,
        effective_registration_open=(
            competition.deleted_at is None and competition.status == "open" and now_utc() < _as_utc(competition.registration_deadline)
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
        created_by_username=actor_label(registration, "created_by"),
        updated_by_username=actor_label(registration, "updated_by"),
        created_at=registration.created_at,
        updated_at=registration.updated_at,
    )


def _mutable_competition(db: Session, competition_id: str) -> Competition:
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
    return competition


def _require_late_reason(competition: Competition, reason: str | None) -> None:
    late = competition.status == "closed" or now_utc() >= _as_utc(competition.registration_deadline)
    if late and not (reason and reason.strip()):
        raise HTTPException(status_code=422, detail="報名截止後的操作必須填寫原因")


def _idempotent_registration(db, request_id, action, competition_id=None, *, actor, fingerprint):
    audit = db.scalar(select(RegistrationAudit).where(RegistrationAudit.idempotency_key == request_id))
    if not audit:
        return None
    if (audit.actor_kind != actor.kind or audit.admin_id != actor.admin_id
        or audit.actor_visit_id != actor.visit_id or audit.request_fingerprint != fingerprint
        or audit.action != action or (competition_id and audit.competition_id != competition_id)):
        raise HTTPException(409, "此操作識別碼已用於其他操作")
    return db.get(CompetitionRegistration, audit.registration_id)


def _registration_audit(
    registration: CompetitionRegistration,
    admin_id: str | None,
    action: str,
    changes: dict[str, dict[str, object]],
    reason: str | None,
    request_id: str,
    actor: Actor,
    fingerprint: str,
) -> RegistrationAudit:
    return RegistrationAudit(
        registration_id=registration.id,
        competition_id=registration.competition_id,
        admin_id=actor.admin_id,
        actor_kind=actor.kind,
        actor_visit_id=actor.visit_id,
        request_fingerprint=fingerprint,
        action=action,
        changes_json=json.dumps(changes, ensure_ascii=False),
        reason=reason.strip() if reason else None,
        idempotency_key=request_id,
    )


def _mutate_registration(
    db: Session,
    auth: tuple[Admin, LoginSession] | PublicVisit,
    registration_id: str,
    payload: RegistrationMutation | RegistrationDietUpdate,
    action: str,
) -> AdminRegistration:
    admin_id = _begin_immediate(db, auth)
    actor = actor_from_auth(auth)
    fingerprint = request_fingerprint(registration_id, payload)
    duplicate = _idempotent_registration(db, payload.request_id, action, actor=actor, fingerprint=fingerprint)
    if duplicate:
        db.rollback()
        return _registration_response(duplicate)
    registration = db.get(CompetitionRegistration, registration_id)
    if not registration:
        db.rollback()
        raise HTTPException(status_code=404, detail="找不到報名紀錄")
    if actor.kind == "public":
        raise HTTPException(404, "找不到報名紀錄")
    competition = _mutable_competition(db, registration.competition_id)
    if actor.kind == "public":
        require_member_open(competition)
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
    registration.updated_by_admin_id = actor.admin_id
    registration.updated_by_visit_id = actor.visit_id
    registration.updated_by_kind = actor.kind
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
        actor,
        fingerprint,
    ))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="此操作已完成或資料已變更") from error
    return _registration_response(registration)


def create_registration_service(db, auth, competition_id, payload):
    admin_id = _begin_immediate(db, auth)
    actor = actor_from_auth(auth)
    fingerprint = request_fingerprint(competition_id, payload)
    duplicate = _idempotent_registration(db, payload.request_id, "create", competition_id, actor=actor, fingerprint=fingerprint)
    if duplicate:
        db.rollback()
        return _registration_response(duplicate)
    competition = _mutable_competition(db, competition_id)
    if actor.kind == "public":
        require_member_open(competition)
    if competition.status == "draft":
        db.rollback()
        raise HTTPException(status_code=409, detail="草稿比賽不接受報名")
    _require_late_reason(competition, payload.reason)
    member = db.get(Member, payload.member_id)
    if not member or not member.is_active:
        db.rollback()
        raise HTTPException(status_code=409, detail="只能選取啟用中的會員")
    try:
        registration = _create_registration_in_transaction(db, competition, member, payload, actor, fingerprint)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="報名已存在或同一操作已完成") from error
    return _registration_response(registration)


def _create_registration_in_transaction(db, competition, member, payload, actor, fingerprint):
    """Caller owns BEGIN IMMEDIATE, authorization, competition-state checks and commit."""
    competition_id = competition.id
    admin_id = actor.admin_id
    existing = db.scalar(select(CompetitionRegistration).where(
        CompetitionRegistration.competition_id == competition_id,
        CompetitionRegistration.member_id == member.id,
        CompetitionRegistration.status != "cancelled",
    ))
    if existing:
        raise HTTPException(status_code=409, detail="這個名字已登記報名；若需確認、更正或取消，請洽管理員")
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
        created_by_kind=actor.kind,
        updated_by_kind=actor.kind,
        created_by_visit_id=actor.visit_id,
        updated_by_visit_id=actor.visit_id,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    competition.next_sequence += 1
    db.add(registration)
    db.flush()
    db.add(_registration_audit(
        registration, admin_id, "create",
        {"status": {"before": None, "after": registration.status}},
        payload.reason, payload.request_id, actor, fingerprint,
    ))
    return registration
