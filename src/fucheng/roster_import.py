"""Atomic import of an explicitly reviewed, all-confirmed roster into an empty draft."""
import json
from typing import Annotated

from fastapi import Depends, HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Competition, CompetitionAudit, CompetitionRegistration, Member, MemberAudit, now_utc
from .registrations import (_begin_immediate, _changes, _competition_response,
    _create_registration_in_transaction, _idempotent_registration, _member_values,
    actor_from_auth, request_fingerprint)
from .schemas import AdminCompetition, Diet, RegistrationCreate, StrictInput
from .security import token_hash


class ConfirmedRosterRow(StrictInput):
    source_ref: str = Field(min_length=1, max_length=100)
    member_id: str | None = Field(default=None, min_length=1, max_length=36)
    create_member: bool = False
    name: str = Field(min_length=1, max_length=100)
    level: int = Field(ge=1, le=10)
    diet: Diet | None = None

    @field_validator("source_ref", "name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("欄位不可空白")
        return value.strip()

    @model_validator(mode="after")
    def explicit_identity(self):
        if bool(self.member_id) == self.create_member:
            raise ValueError("必須明確指定既有會員或確認新增會員")
        return self


class ConfirmedRosterImport(StrictInput):
    version: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=64)
    reason: str = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    rows: list[ConfirmedRosterRow] = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip():
            raise ValueError("請填寫已確認名單的來源與原因")
        return value.strip()

    @model_validator(mode="after")
    def unique_rows(self):
        refs = [row.source_ref for row in self.rows]
        ids = [row.member_id for row in self.rows if row.member_id]
        new_names = [row.name for row in self.rows if row.create_member]
        if len(set(refs)) != len(refs) or len(set(ids)) != len(ids) or len(set(new_names)) != len(new_names):
            raise ValueError("來源位置、會員或新會員重複")
        return self


def import_confirmed_roster(db, auth, competition_id, payload):
    try:
        admin_id = _begin_immediate(db, auth)
        actor = actor_from_auth(auth)
        fingerprint = request_fingerprint(competition_id, payload)
        keys = [token_hash(f"confirmed-roster:{payload.request_id}:{index}") for index in range(len(payload.rows))]
        previous = _idempotent_registration(db, keys[0], "create", competition_id,
            actor=actor, fingerprint=fingerprint)
        if previous:
            result = _competition_response(db, db.get(Competition, competition_id))
            db.rollback()
            return result
        competition = db.get(Competition, competition_id)
        if not competition:
            raise HTTPException(404, "找不到比賽")
        if competition.deleted_at or competition.status != "draft" or competition.version != payload.version:
            raise HTTPException(409, "整份正取名單僅可匯入指定版本的空白草稿")
        if db.scalar(select(CompetitionRegistration.id).where(CompetitionRegistration.competition_id == competition_id).limit(1)):
            raise HTTPException(409, "比賽已有報名紀錄，不能整份匯入")
        if len(payload.rows) > competition.capacity:
            raise HTTPException(409, "正取名單超過名額，請先確認名額與候補安排")
        before_version = competition.version
        before_notes = competition.notes
        provenance = []
        for row, key in zip(payload.rows, keys):
            if row.create_member:
                # Matching is a review step; writes never guess from fuzzy names.
                if db.scalar(select(Member.id).where(Member.name == row.name).limit(1)):
                    raise HTTPException(409, "新會員姓名已有紀錄，請先人工確認對應")
                member = Member(name=row.name, level=row.level, diet="unset", is_active=True)
                db.add(member)
                db.flush()
                db.add(MemberAudit(member_id=member.id, admin_id=admin_id, action="create",
                    changes_json=json.dumps(_changes({}, _member_values(member)), ensure_ascii=False)))
            else:
                member = db.get(Member, row.member_id)
                if not member or not member.is_active or member.name != row.name or member.level != row.level:
                    raise HTTPException(409, "會員資料與已確認名單不符，請重新核對")
            registration = _create_registration_in_transaction(db, competition, member,
                RegistrationCreate(member_id=member.id, diet=row.diet, reason=payload.reason, request_id=key),
                actor, fingerprint)
            if registration.status != "confirmed":
                raise HTTPException(409, "無法將整份名單列為正取，匯入已回滾")
            provenance.append({"source_ref": row.source_ref, "member_id": member.id,
                "registration_id": registration.id, "new_member": row.create_member})
        # Never expose an intermediate open competition. New applications stay disabled.
        if payload.notes is not None:
            competition.notes = payload.notes
        competition.status = "closed"
        competition.version += 1
        competition.updated_at = now_utc()
        db.add(CompetitionAudit(competition_id=competition.id, admin_id=admin_id,
            action="import_confirmed", reason=payload.reason,
            changes_json=json.dumps({"status": {"before": "draft", "after": "closed"},
                "version": {"before": before_version, "after": competition.version},
                "notes": {"before": before_notes, "after": competition.notes},
                "import_rows": {"before": None, "after": provenance}}, ensure_ascii=False)))
        db.commit()
        return _competition_response(db, competition)
    except Exception:
        db.rollback()
        raise


def install_roster_import_route(app, get_db, require_csrf):
    Db = Annotated[Session, Depends(get_db)]
    Write = Annotated[tuple, Depends(require_csrf)]

    @app.post("/api/admin/competitions/{competition_id}/import-confirmed-roster", response_model=AdminCompetition)
    def import_roster(competition_id: str, payload: ConfirmedRosterImport, db: Db, auth: Write):
        return import_confirmed_roster(db, auth, competition_id, payload)
