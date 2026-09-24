"""Rich announcements and private media metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0009_announcement_media"
down_revision = "0008_arrangement_grid"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("announcement_media",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("announcement_id", sa.String(36), sa.ForeignKey("announcements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("filename", sa.String(50), unique=True, nullable=False),
        sa.Column("mime_type", sa.String(20), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_announcement_media_announcement_id", "announcement_media", ["announcement_id"])
    op.add_column("announcements", sa.Column("body_format", sa.String(10), nullable=False, server_default="plain"))
    op.add_column("announcements", sa.Column("photo_id", sa.String(36), nullable=True))


def downgrade():
    raise RuntimeError("請使用升級前的備份還原，避免遺失公告照片與稽核")
