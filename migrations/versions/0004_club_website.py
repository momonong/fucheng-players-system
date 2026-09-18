"""Club homepage announcements with transactional admin audit."""
from alembic import op
import sqlalchemy as sa

revision = "0004_club_website"
down_revision = "0003_public_registration"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("announcements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_announcements_version"))
    op.create_table("announcement_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("announcement_id", sa.String(36), sa.ForeignKey("announcements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("changes_json", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(64), unique=True, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_announcement_audits_announcement_id", "announcement_audits", ["announcement_id"])


def downgrade():
    raise RuntimeError("請使用升級前的備份還原，避免遺失公告與稽核")
