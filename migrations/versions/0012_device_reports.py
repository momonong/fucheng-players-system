"""Append-only device host reports, independent of member/admin business records."""
from alembic import op
import sqlalchemy as sa

revision = "0012_device_reports"
down_revision = "0011_admin_management"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("device_deployment_reports",
        sa.Column("report_id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 262144", name="ck_device_report_size"))
    op.create_index("ix_device_deployment_reports_device_id", "device_deployment_reports", ["device_id"])
    op.create_index("ix_device_deployment_reports_received_at", "device_deployment_reports", ["received_at"])
    for action in ("UPDATE", "DELETE"):
        op.execute(f"CREATE TRIGGER device_reports_no_{action.lower()} BEFORE {action} ON device_deployment_reports "
                   "BEGIN SELECT RAISE(ABORT, 'device reports are append-only'); END")


def downgrade():
    raise RuntimeError("請以匹配 image/schema 的備份還原至新目標，保留已接收報告及故障庫")
