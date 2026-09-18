"""Public club information and administrator-owned announcements."""
import hashlib
import json
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Announcement, AnnouncementAudit, Competition, now_utc
from .registrations import _begin_immediate, _changes
from .schemas import AuditEntry


class AnnouncementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=10000)
    is_published: bool = False
    is_pinned: bool = False
    request_id: str = Field(min_length=8, max_length=64)

    @field_validator("title", "body")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("內容不可空白")
        return value


class AnnouncementUpdate(AnnouncementInput):
    version: int = Field(ge=1)


class PublicAnnouncement(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    body: str
    is_pinned: bool
    published_at: datetime
    updated_at: datetime


class AdminAnnouncement(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    body: str
    is_pinned: bool
    is_published: bool
    version: int
    published_at: datetime | None
    updated_at: datetime


class ScheduleItem(BaseModel):
    id: str
    name: str
    competition_date: date
    registration_deadline: datetime
    status: Literal["open", "closed", "ended", "cancelled"]
    notes: str | None


def save_announcement(db, auth, payload, announcement_id=None):
    admin_id = _begin_immediate(db, auth)
    fingerprint = hashlib.sha256(json.dumps(
        {"target": announcement_id, **payload.model_dump(exclude={"request_id"})},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    previous = db.scalar(select(AnnouncementAudit).where(AnnouncementAudit.request_id == payload.request_id))
    if previous:
        if previous.admin_id != admin_id or previous.fingerprint != fingerprint:
            raise HTTPException(409, "請重新送出這次操作")
        return db.get(Announcement, previous.announcement_id)
    values = payload.model_dump(exclude={"request_id", "version"})
    before = {}
    row = db.get(Announcement, announcement_id) if announcement_id else None
    if announcement_id:
        if not row:
            raise HTTPException(404, "找不到公告")
        if row.version != payload.version:
            raise HTTPException(409, "公告已被其他管理員更新，請重新載入後再編輯；目前輸入已保留")
        before = {key: getattr(row, key) for key in values}
        row.version += 1
        for key, value in values.items():
            setattr(row, key, value)
    else:
        row = Announcement(**values)
        db.add(row)
    if values["is_published"] and not before.get("is_published"):
        row.published_at = now_utc()
    row.updated_at = now_utc()
    db.flush()
    db.add(AnnouncementAudit(announcement_id=row.id, admin_id=admin_id,
        action="update" if announcement_id else "create",
        changes_json=json.dumps(_changes(before, values), ensure_ascii=False),
        request_id=payload.request_id, fingerprint=fingerprint))
    db.commit()
    return row


def install_website_routes(app, get_db, current_auth, require_csrf):
    Db = Annotated[Session, Depends(get_db)]
    Auth = Annotated[tuple, Depends(current_auth)]
    Write = Annotated[tuple, Depends(require_csrf)]

    @app.get("/api/public/announcements", response_model=list[PublicAnnouncement])
    def announcements(db: Db):
        return list(db.scalars(select(Announcement).where(Announcement.is_published.is_(True))
            .order_by(Announcement.is_pinned.desc(), Announcement.published_at.desc(), Announcement.id)))

    @app.get("/api/public/schedule", response_model=list[ScheduleItem])
    def schedule(db: Db):
        # Drafts stay private. Clock-derived closure agrees with registration enforcement.
        rows = db.scalars(select(Competition).where(Competition.deleted_at.is_(None), Competition.status != "draft")
            .order_by(Competition.competition_date.desc(), Competition.id))
        now = now_utc()
        return [ScheduleItem(id=row.id, name=row.name, competition_date=row.competition_date,
            registration_deadline=row.registration_deadline, notes=row.notes,
            status="closed" if row.status == "open" and row.registration_deadline <= now else row.status)
            for row in rows]

    @app.get("/api/admin/announcements", response_model=list[AdminAnnouncement])
    def admin_announcements(db: Db, _auth: Auth):
        return list(db.scalars(select(Announcement).order_by(Announcement.updated_at.desc(), Announcement.id)))

    @app.post("/api/admin/announcements", response_model=AdminAnnouncement, status_code=201)
    def create(payload: AnnouncementInput, db: Db, auth: Write):
        return save_announcement(db, auth, payload)

    @app.put("/api/admin/announcements/{announcement_id}", response_model=AdminAnnouncement)
    def update(announcement_id: str, payload: AnnouncementUpdate, db: Db, auth: Write):
        return save_announcement(db, auth, payload, announcement_id)

    @app.get("/api/admin/announcements/{announcement_id}/history", response_model=list[AuditEntry])
    def history(announcement_id: str, db: Db, _auth: Auth):
        if not db.get(Announcement, announcement_id):
            raise HTTPException(404, "找不到公告")
        rows = db.scalars(select(AnnouncementAudit).where(AnnouncementAudit.announcement_id == announcement_id)
            .order_by(AnnouncementAudit.created_at.desc(), AnnouncementAudit.id))
        return [AuditEntry(id=row.id, action=row.action, changes=json.loads(row.changes_json),
            admin_username=row.admin.username, created_at=row.created_at) for row in rows]
