"""新增比賽與管理員報名名單。"""

from alembic import op
import sqlalchemy as sa


revision = "0002_competition_registration"
down_revision = "0001_member_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("competition_date", sa.Date(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("registration_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("next_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("capacity >= 1", name="ck_competitions_capacity"),
        sa.CheckConstraint(
            "status IN ('draft', 'open', 'closed', 'ended', 'cancelled')",
            name="ck_competitions_status",
        ),
        sa.CheckConstraint("next_sequence >= 1", name="ck_competitions_next_sequence"),
    )
    op.create_index("ix_competitions_name", "competitions", ["name"])
    op.create_index("ix_competitions_competition_date", "competitions", ["competition_date"])
    op.create_index("ix_competitions_registration_deadline", "competitions", ["registration_deadline"])
    op.create_index("ix_competitions_status", "competitions", ["status"])

    op.create_table(
        "competition_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "competition_id",
            sa.String(36),
            sa.ForeignKey("competitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("changes_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_competition_audits_competition_id", "competition_audits", ["competition_id"])
    op.create_index("ix_competition_audits_admin_id", "competition_audits", ["admin_id"])
    op.create_index("ix_competition_audits_created_at", "competition_audits", ["created_at"])

    op.create_table(
        "competition_registrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "competition_id",
            sa.String(36),
            sa.ForeignKey("competitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("member_id", sa.String(36), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("diet", sa.String(20), nullable=False),
        sa.Column("hard_level_snapshot", sa.Integer(), nullable=False),
        sa.Column("queue_sequence", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_admin_id",
            sa.String(36),
            sa.ForeignKey("admins.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "updated_by_admin_id",
            sa.String(36),
            sa.ForeignKey("admins.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('confirmed', 'waitlisted', 'cancelled')",
            name="ck_competition_registrations_status",
        ),
        sa.CheckConstraint(
            "diet IN ('unset', 'omnivore', 'vegetarian')",
            name="ck_competition_registrations_diet",
        ),
        sa.CheckConstraint(
            "hard_level_snapshot BETWEEN 1 AND 10",
            name="ck_competition_registrations_level",
        ),
        sa.CheckConstraint("queue_sequence >= 1", name="ck_competition_registrations_sequence"),
        sa.UniqueConstraint("competition_id", "queue_sequence", name="uq_registration_sequence"),
    )
    op.create_index("ix_competition_registrations_competition_id", "competition_registrations", ["competition_id"])
    op.create_index("ix_competition_registrations_member_id", "competition_registrations", ["member_id"])
    op.create_index("ix_competition_registrations_status", "competition_registrations", ["status"])
    op.create_index("ix_competition_registrations_hard_level_snapshot", "competition_registrations", ["hard_level_snapshot"])
    op.create_index("ix_competition_registrations_created_by_admin_id", "competition_registrations", ["created_by_admin_id"])
    op.create_index("ix_competition_registrations_updated_by_admin_id", "competition_registrations", ["updated_by_admin_id"])
    op.create_index(
        "uq_active_registration_member",
        "competition_registrations",
        ["competition_id", "member_id"],
        unique=True,
        sqlite_where=sa.text("status != 'cancelled'"),
    )

    op.create_table(
        "registration_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "registration_id",
            sa.String(36),
            sa.ForeignKey("competition_registrations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "competition_id",
            sa.String(36),
            sa.ForeignKey("competitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("changes_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_registration_audits_registration_id", "registration_audits", ["registration_id"])
    op.create_index("ix_registration_audits_competition_id", "registration_audits", ["competition_id"])
    op.create_index("ix_registration_audits_admin_id", "registration_audits", ["admin_id"])
    op.create_index("ix_registration_audits_idempotency_key", "registration_audits", ["idempotency_key"], unique=True)
    op.create_index("ix_registration_audits_created_at", "registration_audits", ["created_at"])


def downgrade() -> None:
    op.drop_table("registration_audits")
    op.drop_table("competition_registrations")
    op.drop_table("competition_audits")
    op.drop_table("competitions")
