"""Recoverable competition deletion; keep all rosters and audit history."""
from alembic import op
import sqlalchemy as sa

revision = "0005_competition_deletion"
down_revision = "0004_club_website"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("competitions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError("請使用升級前的備份還原，避免已刪除比賽重新公開")
