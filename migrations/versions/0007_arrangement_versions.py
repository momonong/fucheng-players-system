"""Append-only arrangement snapshots; do not invent an initial historical baseline."""
from alembic import op
import sqlalchemy as sa

revision = "0007_arrangement_versions"
down_revision = "0006_competition_level"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("arrangement_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("competition_id", sa.String(36), sa.ForeignKey("competitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("editor_label", sa.String(100), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_name", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rows_json", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(64), unique=True, nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.UniqueConstraint("competition_id", "sequence", name="uq_arrangement_sequence"),
        sa.CheckConstraint("sequence >= 0", name="ck_arrangement_sequence"))
    op.create_index("ix_arrangement_versions_competition_id", "arrangement_versions", ["competition_id"])


def downgrade():
    raise RuntimeError("不可丟棄安排版本；請以升級前備份還原至新目標，搭配相符程式／schema，保留故障庫")
