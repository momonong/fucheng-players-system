from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
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
    body_format: Mapped[str] = mapped_column(String(10), default="plain")
    photo_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class AnnouncementMedia(Base):
    __tablename__ = "announcement_media"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    announcement_id: Mapped[str] = mapped_column(ForeignKey("announcements.id", ondelete="RESTRICT"), index=True)
    filename: Mapped[str] = mapped_column(String(50), unique=True)
    mime_type: Mapped[str] = mapped_column(String(20))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


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
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class AdminAudit(Base):
    __tablename__ = "admin_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_admin_id: Mapped[str | None] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"), nullable=True)
    target_admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(20))
    changes_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc, index=True)
    actor: Mapped[Admin | None] = relationship(foreign_keys=[actor_admin_id])
    target: Mapped[Admin] = relationship(foreign_keys=[target_admin_id])


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    admin: Mapped[Admin] = relationship()


class DeploymentReport(Base):
    """The administrator's current host preflight report, stored in the backup DB."""
    __tablename__ = "deployment_reports"
    __table_args__ = (CheckConstraint("id = 1", name="ck_deployment_report_singleton"),
                      CheckConstraint("version >= 1", name="ck_deployment_report_version"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    report_json: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by_admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"))
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime())


class DeviceDeploymentReport(Base):
    """Immutable device upload; it never replaces the manually reviewed report."""
    __tablename__ = "device_deployment_reports"
    __table_args__ = (CheckConstraint("size_bytes > 0 AND size_bytes <= 262144", name="ck_device_report_size"),)
    report_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    digest: Mapped[str] = mapped_column(String(64))
    report_json: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


class DeploymentReportAudit(Base):
    __tablename__ = "deployment_report_audits"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_deployment_report_audit_version"),
                      UniqueConstraint("version", name="uq_deployment_report_audit_version"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class DeploymentDiagnosticRun(Base):
    """Immutable report/request identity with a durable, separately mutable delivery state."""
    __tablename__ = "deployment_diagnostic_runs"
    __table_args__ = (
        CheckConstraint("size_bytes > 0 AND size_bytes <= 262144", name="ck_diagnostic_size"),
        CheckConstraint("send_state IN ('not_configured','unknown','rejected','received')", name="ck_diagnostic_send_state"),
        UniqueConstraint("report_version", name="uq_diagnostic_report_version"),
    )
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    report_version: Mapped[int] = mapped_column(Integer)
    report_json: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    endpoint: Mapped[str] = mapped_column(String(200))
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    send_state: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(String(400))
    receipt_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())


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
        CheckConstraint("registration_mode IN ('individual', 'doubles')", name="ck_competitions_registration_mode"),
        CheckConstraint("doubles_min_total_level IS NULL OR doubles_min_total_level BETWEEN 2 AND 20", name="ck_competitions_doubles_min_level"),
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
    registration_mode: Mapped[str] = mapped_column(String(12), default="individual", server_default="individual")
    doubles_min_total_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


class ArrangementVersion(Base):
    """Append-only full snapshots; sequence zero is the explicit initial baseline."""
    __tablename__ = "arrangement_versions"
    __table_args__ = (
        UniqueConstraint("competition_id", "sequence", name="uq_arrangement_sequence"),
        CheckConstraint("sequence >= 0", name="ck_arrangement_sequence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id", ondelete="RESTRICT"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(100))
    editor_label: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"))
    actor_name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    rows_json: Mapped[str] = mapped_column(Text)
    layout_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)


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


class ArrangementWorkspace(Base):
    __tablename__ = "arrangement_workspaces"
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id", ondelete="RESTRICT"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    layout_json: Mapped[str] = mapped_column(Text)
    initial_layout_json: Mapped[str] = mapped_column(Text)
    initialized_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"))
    __table_args__ = (CheckConstraint("revision >= 1", name="ck_arrangement_revision"),)


class ArrangementOperation(Base):
    __tablename__ = "arrangement_operations"
    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id", ondelete="RESTRICT"), index=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    receipt_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)


class DoublesEntry(Base):
    __tablename__ = "doubles_entries"
    __table_args__ = (
        UniqueConstraint("id", "competition_id", name="uq_doubles_entry_competition"),
        UniqueConstraint("competition_id", "sequence", name="uq_doubles_sequence"),
        CheckConstraint("status IN ('waiting_partner','pending','confirmed','waitlisted','cancelled')", name="ck_doubles_status"),
        CheckConstraint("member_count IN (1,2) AND (status='cancelled' OR (status='waiting_partner' AND member_count=1) OR (status IN ('pending','confirmed','waitlisted') AND member_count=2))", name="ck_doubles_member_count"),
        CheckConstraint("version >= 1 AND sequence >= 1", name="ck_doubles_version_sequence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    member_count: Mapped[int] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
    members: Mapped[list["DoublesEntryMember"]] = relationship(order_by="DoublesEntryMember.position")


class DoublesEntryMember(Base):
    __tablename__ = "doubles_entry_members"
    __table_args__ = (
        ForeignKeyConstraint(["entry_id", "competition_id"], ["doubles_entries.id", "doubles_entries.competition_id"], ondelete="RESTRICT"),
        UniqueConstraint("entry_id", "position", name="uq_doubles_member_position"),
        UniqueConstraint("entry_id", "member_id", name="uq_doubles_entry_member"),
        CheckConstraint("position IN (1,2)", name="ck_doubles_member_position"),
        CheckConstraint("level_snapshot BETWEEN 1 AND 10", name="ck_doubles_level_snapshot"),
        Index("uq_doubles_active_member", "competition_id", "member_id", unique=True, sqlite_where=text("is_active=1")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entry_id: Mapped[str] = mapped_column(String(36), index=True)
    competition_id: Mapped[str] = mapped_column(String(36), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    level_snapshot: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    member: Mapped[Member] = relationship()


class DoublesAudit(Base):
    __tablename__ = "doubles_audits"
    __table_args__ = (actor_constraint("actor", admin_column="admin_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entry_id: Mapped[str] = mapped_column(ForeignKey("doubles_entries.id", ondelete="RESTRICT"), index=True)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id", ondelete="RESTRICT"), index=True)
    actor_kind: Mapped[str] = mapped_column(String(10))
    admin_id: Mapped[str | None] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"), nullable=True)
    actor_visit_id: Mapped[str | None] = mapped_column(ForeignKey("public_visits.id", ondelete="RESTRICT"), nullable=True)
    action: Mapped[str] = mapped_column(String(30))
    changes_json: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc, index=True)
    admin: Mapped[Admin | None] = relationship()


class DoublesReceipt(Base):
    __tablename__ = "doubles_receipts"
    __table_args__ = (actor_constraint("actor", admin_column="admin_id"),)
    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id", ondelete="RESTRICT"), index=True)
    actor_kind: Mapped[str] = mapped_column(String(10))
    admin_id: Mapped[str | None] = mapped_column(ForeignKey("admins.id", ondelete="RESTRICT"), nullable=True)
    actor_visit_id: Mapped[str | None] = mapped_column(ForeignKey("public_visits.id", ondelete="RESTRICT"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now_utc)
