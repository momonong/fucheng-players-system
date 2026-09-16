from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, UTCDateTime


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


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
