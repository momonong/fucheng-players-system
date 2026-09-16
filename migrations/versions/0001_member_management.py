"""建立第一版會員管理資料表。"""
from alembic import op
import sqlalchemy as sa

revision = "0001_member_management"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_admins_username", "admins", ["username"], unique=True)
    op.create_table(
        "members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("distinguishing_note", sa.String(100)),
        sa.Column("legacy_number", sa.String(50)),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("diet", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("level BETWEEN 1 AND 10", name="ck_members_level"),
        sa.CheckConstraint("diet IN ('unset', 'omnivore', 'vegetarian')", name="ck_members_diet"),
        sa.UniqueConstraint("legacy_number"),
    )
    op.create_index("ix_members_name", "members", ["name"])
    op.create_index("ix_members_level", "members", ["level"])
    op.create_index("ix_members_is_active", "members", ["is_active"])
    op.create_table(
        "fee_periods",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_fee_period_dates"),
        sa.UniqueConstraint("starts_on", "ends_on", name="uq_fee_period_range"),
    )
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_login_sessions_token_hash", "login_sessions", ["token_hash"], unique=True)
    op.create_index("ix_login_sessions_admin_id", "login_sessions", ["admin_id"])
    op.create_index("ix_login_sessions_expires_at", "login_sessions", ["expires_at"])
    op.create_table(
        "member_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("member_id", sa.String(36), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("changes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_member_audits_member_id", "member_audits", ["member_id"])
    op.create_index("ix_member_audits_admin_id", "member_audits", ["admin_id"])
    op.create_index("ix_member_audits_created_at", "member_audits", ["created_at"])
    op.create_table(
        "member_fee_statuses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("member_id", sa.String(36), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fee_period_id", sa.String(36), sa.ForeignKey("fee_periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("recorded_by_admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('paid', 'unpaid', 'waived')", name="ck_member_fee_status"),
        sa.UniqueConstraint("member_id", "fee_period_id", name="uq_member_fee_period"),
    )
    op.create_index("ix_member_fee_statuses_member_id", "member_fee_statuses", ["member_id"])
    op.create_index("ix_member_fee_statuses_fee_period_id", "member_fee_statuses", ["fee_period_id"])


def downgrade() -> None:
    op.drop_table("member_fee_statuses")
    op.drop_table("member_audits")
    op.drop_table("login_sessions")
    op.drop_table("fee_periods")
    op.drop_table("members")
    op.drop_table("admins")
