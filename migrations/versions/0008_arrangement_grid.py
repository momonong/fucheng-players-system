"""Explicit spatial arrangements; legacy snapshots keep unknown positions."""
from alembic import op
import sqlalchemy as sa

revision = "0008_arrangement_grid"
down_revision = "0007_arrangement_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("arrangement_versions", sa.Column("layout_json", sa.Text(), nullable=True))
    op.create_table("arrangement_workspaces",
        sa.Column("competition_id", sa.String(36), sa.ForeignKey("competitions.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("layout_json", sa.Text(), nullable=False),
        sa.Column("initial_layout_json", sa.Text(), nullable=False),
        sa.Column("initialized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_arrangement_revision"))
    op.create_table("arrangement_operations",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("competition_id", sa.String(36), sa.ForeignKey("competitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("receipt_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_arrangement_operations_competition_id", "arrangement_operations", ["competition_id"])


def downgrade():
    raise RuntimeError("不可丟棄布局；以升級前備份還原新目標，保留新庫，搭配相符程式與 schema")
