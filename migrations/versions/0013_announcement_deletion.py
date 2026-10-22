"""Recoverable announcement deletion preserves content, media, and audit history."""
from alembic import op
import sqlalchemy as sa

revision = "0013_announcement_deletion"
down_revision = "0012_device_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("announcements", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError("請以匹配 image/schema 的備份還原至新目標，保留公告、圖片、操作紀錄及故障庫")
