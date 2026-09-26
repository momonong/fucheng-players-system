"""Store the latest administrator-only host report in the existing backup database."""
from alembic import op
import sqlalchemy as sa

revision = "0010_deployment_report"
down_revision = "0009_announcement_media"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("deployment_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by_admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_deployment_report_singleton"),
        sa.CheckConstraint("version >= 1", name="ck_deployment_report_version"))
    op.create_table("deployment_report_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_deployment_report_audit_version"),
        sa.UniqueConstraint("version", name="uq_deployment_report_audit_version"))


def downgrade():
    raise RuntimeError("請使用升級前的備份還原，避免遺失部署報告稽核")
