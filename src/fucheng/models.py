from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, UTCDateTime


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_announcements_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class AnnouncementAudit(Base):
    __tablename__ = "announcement_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    announcement_id: Mapped[str] = mapped_column(ForeignKey("announcements.id", ondelete="RESTRICT"), index=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(20))
    changes_json: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    admin: Mapped[Admin] = relationship()


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    admin: Mapped[Admin] = relationship()


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 10", name="ck_members_level"),
        CheckConstraint("diet IN ('unset', 'omnivore', 'vegetarian')", name="ck_members_diet"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), index=True)
    distinguishing_note: Mapped[str | None] = mapped_column(String(100), nullable=True)
    legacy_number: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    level: Mapped[int] = mapped_column(Integer, index=True)
    diet: Mapped[str] = mapped_column(String(20), default="omnivore")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class MemberAudit(Base):
    __tablename__ = "member_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), index=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    changes_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc, index=True)
    admin: Mapped[Admin] = relationship()


class FeePeriod(Base):
    __tablename__ = "fee_periods"
    __table_args__ = (
        CheckConstraint("ends_on >= starts_on", name="ck_fee_period_dates"),
        UniqueConstraint("starts_on", "ends_on", name="uq_fee_period_range"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    label: Mapped[str] = mapped_column(String(100))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class MemberFeeStatus(Base):
    __tablename__ = "member_fee_statuses"
    __table_args__ = (
        UniqueConstraint("member_id", "fee_period_id", name="uq_member_fee_period"),
        CheckConstraint("status IN ('paid', 'unpaid', 'waived')", name="ck_member_fee_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), index=True)
    fee_period_id: Mapped[str] = mapped_column(ForeignKey("fee_periods.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    recorded_by_admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class Competition(Base):
    __tablename__ = "competitions"
    __table_args__ = (
        CheckConstraint("capacity >= 1", name="ck_competitions_capacity"),
        CheckConstraint(
            "status IN ('draft', 'open', 'closed', 'ended', 'cancelled')",
            name="ck_competitions_status",
        ),
        CheckConstraint("next_sequence >= 1", name="ck_competitions_next_sequence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), index=True)
    competition_date: Mapped[date] = mapped_column(Date, index=True)
    capacity: Mapped[int] = mapped_column(Integer)
    registration_deadline: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    next_sequence: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class CompetitionAudit(Base):
    __tablename__ = "competition_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id", ondelete="RESTRICT"), index=True
    )
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    changes_json: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc, index=True)
    admin: Mapped[Admin] = relationship()


class PublicVisit(Base):
    """Automatic browser context, not a member account or verified identity."""
    __tablename__ = "public_visits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


def actor_constraint(prefix: str, admin_column: str | None = None):
    admin = admin_column or f"{prefix}_admin_id"
    visit = f"{prefix}_visit_id"
    kind = f"{prefix}_kind"
    return CheckConstraint(
        f"({kind}='admin' AND {admin} IS NOT NULL AND {visit} IS NULL) OR "
        f"({kind}='public' AND {admin} IS NULL AND {visit} IS NOT NULL) OR "
        f"({kind}='system' AND {admin} IS NULL AND {visit} IS NULL)",
        name=f"ck_{prefix}_exclusive_actor",
    )


class CompetitionRegistration(Base):
    __tablename__ = "competition_registrations"
    __table_args__ = (
        actor_constraint("created_by"),
        actor_constraint("updated_by"),
        CheckConstraint(
            "status IN ('confirmed', 'waitlisted', 'cancelled')",
            name="ck_competition_registrations_status",
        ),
        CheckConstraint(
            "diet IN ('unset', 'omnivore', 'vegetarian')",
            name="ck_competition_registrations_diet",
        ),
        CheckConstraint(
            "hard_level_snapshot BETWEEN 1 AND 10",
            name="ck_competition_registrations_level",
        ),
        CheckConstraint("queue_sequence >= 1", name="ck_competition_registrations_sequence"),
        CheckConstraint("competition_level BETWEEN 1 AND 10", name="ck_registration_competition_level"),
        UniqueConstraint("competition_id", "queue_sequence", name="uq_registration_sequence"),
        Index(
            "uq_active_registration_member",
            "competition_id",
            "member_id",
            unique=True,
            sqlite_where=text("status != 'cancelled'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id", ondelete="RESTRICT"), index=True
    )
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    diet: Mapped[str] = mapped_column(String(20))
    hard_level_snapshot: Mapped[int] = mapped_column(Integer, index=True)
    competition_level: Mapped[int] = mapped_column(Integer)
    queue_sequence: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_admin_id: Mapped[str | None] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), index=True
    )
    updated_by_admin_id: Mapped[str | None] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), index=True
    )
    created_by_kind: Mapped[str] = mapped_column(String(10), default="admin", server_default="admin")
    created_by_visit_id: Mapped[str | None] = mapped_column(ForeignKey("public_visits.id", ondelete="RESTRICT"), nullable=True)
    updated_by_kind: Mapped[str] = mapped_column(String(10), default="admin", server_default="admin")
    updated_by_visit_id: Mapped[str | None] = mapped_column(ForeignKey("public_visits.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    member: Mapped[Member] = relationship(foreign_keys=[member_id])
    created_by: Mapped[Admin | None] = relationship(foreign_keys=[created_by_admin_id])
    updated_by: Mapped[Admin | None] = relationship(foreign_keys=[updated_by_admin_id])


class RegistrationAudit(Base):
    __tablename__ = "registration_audits"
    __table_args__ = (actor_constraint("actor", admin_column="admin_id"),)
    actor_kind: Mapped[str] = mapped_column(String(10), default="admin", server_default="admin")
    actor_visit_id: Mapped[str | None] = mapped_column(ForeignKey("public_visits.id", ondelete="RESTRICT"), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    registration_id: Mapped[str] = mapped_column(
        ForeignKey("competition_registrations.id", ondelete="RESTRICT"), index=True
    )
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id", ondelete="RESTRICT"), index=True
    )
    admin_id: Mapped[str | None] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    changes_json: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc, index=True)
    admin: Mapped[Admin | None] = relationship()


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
