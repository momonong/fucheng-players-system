"""Manage administrator lifecycle without inventing historical creation events."""
from alembic import op
import sqlalchemy as sa

revision = "0011_admin_management"
down_revision = "0010_deployment_report"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admins", sa.Column("display_name", sa.String(100), nullable=True))
    op.add_column("admins", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("admins", sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")))
    # Existing accounts keep their real creation time; migration does not claim
    # that an administrator changed them or create an audit event.
    op.add_column("admins", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE admins SET updated_at = created_at")
    with op.batch_alter_table("admins") as batch:
        batch.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.create_table("admin_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("target_admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("changes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_admin_audits_target_admin_id", "admin_audits", ["target_admin_id"])
    op.create_index("ix_admin_audits_created_at", "admin_audits", ["created_at"])


def downgrade():
    raise RuntimeError("請使用升級前的匹配備份還原，避免遺失管理員操作紀錄")
