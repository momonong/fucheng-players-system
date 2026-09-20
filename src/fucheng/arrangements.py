"""Immutable arrangement snapshots with a full-roster compare-and-save boundary."""
import hashlib
import json
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import Admin, ArrangementVersion, Competition, CompetitionAudit, CompetitionRegistration, now_utc
from .registrations import _begin_immediate
from .schemas import StrictInput


class ArrangementRow(BaseModel):
    registration_id: str
    member_id: str
    member_name: str
    distinguishing_note: str | None
    queue_sequence: int
    competition_level: int
    version: int


class VersionSummary(BaseModel):
    id: str
    competition_id: str
    sequence: int
    label: str
    editor_label: str
    note: str | None
    admin_id: str
    actor_name: str
    created_at: datetime


class SavedArrangement(VersionSummary):
    rows: list[ArrangementRow]


class ArrangementState(BaseModel):
    editable: bool
    rows: list[ArrangementRow]
    state_token: str
    latest: SavedArrangement | None
    versions: list[VersionSummary]


class SaveArrangement(StrictInput):
    request_id: str = Field(min_length=8, max_length=64)
    state_token: str = Field(min_length=64, max_length=64)
    base_version_id: str = Field(min_length=1, max_length=36)
    label: str | None = Field(default=None, max_length=100)
    editor_label: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("label", "editor_label", "note")
    @classmethod
    def optional_text(cls, value):
        return value.strip() or None if value is not None else None


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def require_competition(db, competition_id, *, mutable=False):
    competition = db.get(Competition, competition_id)
    if not competition:
        raise HTTPException(404, "找不到比賽")
    if mutable and (competition.deleted_at or competition.status not in {"open", "closed"}):
        raise HTTPException(409, "只有未刪除的開放或截止場次可安排級數")
    return competition


def roster(db, competition_id):
    # Caller owns an actual SQLite transaction (also for GET), not legacy implicit SELECTs.
    registrations = db.scalars(select(CompetitionRegistration).where(
        CompetitionRegistration.competition_id == competition_id
    ).order_by(CompetitionRegistration.queue_sequence, CompetitionRegistration.id)).all()
    result = []
    for row in registrations:
        result.append({"registration_id": row.id, "member_id": row.member_id,
            "member_name": row.member.name, "distinguishing_note": row.member.distinguishing_note,
            "queue_sequence": row.queue_sequence, "competition_level": row.competition_level,
            "version": row.version, "status": row.status})
    return result


def confirmed_rows(rows):
    return [{key: value for key, value in row.items() if key != "status"} for row in rows if row["status"] == "confirmed"]


def summary(row):
    return VersionSummary(**{key: getattr(row, key) for key in VersionSummary.model_fields})


def saved(row):
    return SavedArrangement(**summary(row).model_dump(), rows=json.loads(row.rows_json))


def state(db, competition):
    rows = roster(db, competition.id)
    versions = db.scalars(select(ArrangementVersion).where(ArrangementVersion.competition_id == competition.id)
        .order_by(ArrangementVersion.sequence.desc())).all()
    latest = versions[0] if versions else None
    token = digest({"competition_id": competition.id, "version": competition.version,
        "status": competition.status, "deleted_at": competition.deleted_at,
        "rows": rows, "latest_id": latest.id if latest else None})
    return ArrangementState(editable=not competition.deleted_at and competition.status in {"open", "closed"}, rows=confirmed_rows(rows), state_token=token,
        latest=saved(latest) if latest else None, versions=[summary(row) for row in versions])


def append_version(db, competition, admin_id, sequence, rows, *, payload=None, fingerprint=None):
    admin = db.get(Admin, admin_id)
    timestamp = now_utc().replace(microsecond=0)
    row = ArrangementVersion(competition_id=competition.id, sequence=sequence,
        label=(payload.label or f"版本 {sequence}") if payload else "起始基準",
        editor_label=(payload.editor_label or admin.username) if payload else admin.username,
        note=payload.note if payload else None, admin_id=admin_id, actor_name=admin.username,
        created_at=timestamp, rows_json=json.dumps(rows, ensure_ascii=False),
        request_id=payload.request_id if payload else None, fingerprint=fingerprint)
    db.add(row)
    db.flush()
    db.add(CompetitionAudit(competition_id=competition.id, admin_id=admin_id,
        action="arrangement_save" if sequence else "arrangement_initialize",
        created_at=timestamp, reason=payload.note if payload else None,
        changes_json=json.dumps({"arrangement_version": {"before": sequence - 1 if sequence else None,
            "after": sequence}, "version_id": row.id}, ensure_ascii=False)))
    return row


def ensure_initial_baseline(db, competition, admin_id):
    """Caller owns BEGIN IMMEDIATE and commits/rolls back baseline together with its mutation."""
    require_competition(db, competition.id, mutable=True)
    initial = db.scalar(select(ArrangementVersion).where(
        ArrangementVersion.competition_id == competition.id, ArrangementVersion.sequence == 0))
    return initial or append_version(db, competition, admin_id, 0, confirmed_rows(roster(db, competition.id)))


def arrangement_signature(rows):
    # A rename is retained in future snapshots, but is not a fictitious level move.
    return {row["registration_id"]: row["competition_level"] for row in rows}


def initialize(db, auth, competition_id):
    try:
        admin_id = _begin_immediate(db, auth)
        competition = require_competition(db, competition_id, mutable=True)
        ensure_initial_baseline(db, competition, admin_id)
        db.flush()
        result = state(db, competition)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def save_version(db, auth, competition_id, payload):
    try:
        admin_id = _begin_immediate(db, auth)
        fingerprint = digest({"competition_id": competition_id, **payload.model_dump(exclude={"request_id"})})
        duplicate = db.scalar(select(ArrangementVersion).where(ArrangementVersion.request_id == payload.request_id))
        if duplicate:
            if duplicate.admin_id != admin_id or duplicate.fingerprint != fingerprint or duplicate.competition_id != competition_id:
                raise HTTPException(409, "此操作識別碼已用於其他操作")
            result = saved(duplicate)
            db.rollback()
            return result
        competition = require_competition(db, competition_id, mutable=True)
        current = state(db, competition)
        if not current.latest or current.latest.id != payload.base_version_id or current.state_token != payload.state_token:
            raise HTTPException(409, "名單或保存版本已更新，請重新讀取並核對後再保存")
        rows = [row.model_dump() for row in current.rows]
        if arrangement_signature(rows) == arrangement_signature([row.model_dump() for row in current.latest.rows]):
            raise HTTPException(422, "與上次保存相比沒有安排變更")
        row = append_version(db, competition, admin_id, current.latest.sequence + 1, rows, payload=payload, fingerprint=fingerprint)
        db.flush()
        result = saved(row)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def install_arrangement_routes(app, get_db, require_auth, require_csrf):
    @app.get("/api/admin/competitions/{competition_id}/arrangement", response_model=ArrangementState)
    def get_state(competition_id: str, db: Annotated[Session, Depends(get_db)], _auth=Depends(require_auth)):
        db.rollback()
        db.execute(text("BEGIN"))
        return state(db, require_competition(db, competition_id))

    @app.post("/api/admin/competitions/{competition_id}/arrangement/initialize", response_model=ArrangementState)
    def init_state(competition_id: str, db: Annotated[Session, Depends(get_db)], auth=Depends(require_csrf)):
        return initialize(db, auth, competition_id)

    @app.post("/api/admin/competitions/{competition_id}/arrangement/versions", response_model=SavedArrangement)
    def post_version(competition_id: str, payload: SaveArrangement, db: Annotated[Session, Depends(get_db)], auth=Depends(require_csrf)):
        return save_version(db, auth, competition_id, payload)

    @app.get("/api/admin/competitions/{competition_id}/arrangement/versions/{version_id}", response_model=SavedArrangement)
    def get_version(competition_id: str, version_id: str, db: Annotated[Session, Depends(get_db)], _auth=Depends(require_auth)):
        row = db.scalar(select(ArrangementVersion).where(ArrangementVersion.id == version_id, ArrangementVersion.competition_id == competition_id))
        if not row:
            raise HTTPException(404, "找不到保存版本")
        return saved(row)
