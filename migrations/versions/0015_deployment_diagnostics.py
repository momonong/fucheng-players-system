"""Container diagnostic run identity and durable delivery state; old tables unchanged."""
from alembic import op
import sqlalchemy as sa

revision = '0015_deployment_diagnostics'
down_revision = '0014_doubles_registration'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('deployment_diagnostic_runs',
        sa.Column('request_id',sa.String(36),primary_key=True),
        sa.Column('admin_id',sa.String(36),sa.ForeignKey('admins.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('report_version',sa.Integer(),nullable=False),
        sa.Column('report_json',sa.Text(),nullable=False),
        sa.Column('digest',sa.String(64),nullable=False),
        sa.Column('size_bytes',sa.Integer(),nullable=False),
        sa.Column('endpoint',sa.String(200),nullable=False),
        sa.Column('device_id',sa.String(64),nullable=True),
        sa.Column('send_state',sa.String(20),nullable=False),
        sa.Column('detail',sa.String(400),nullable=False),
        sa.Column('receipt_json',sa.Text(),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('report_version',name='uq_diagnostic_report_version'),
        sa.CheckConstraint('size_bytes > 0 AND size_bytes <= 262144',name='ck_diagnostic_size'),
        sa.CheckConstraint("send_state IN ('not_configured','unknown','rejected','received')",name='ck_diagnostic_send_state'))
    op.execute("CREATE TRIGGER diagnostic_runs_no_delete BEFORE DELETE ON deployment_diagnostic_runs BEGIN SELECT RAISE(ABORT, 'diagnostic reports are retained'); END")
    immutable = ('request_id','admin_id','fingerprint','report_version','report_json','digest','size_bytes','endpoint','created_at')
    conditions = ' OR '.join(f'NEW.{name} IS NOT OLD.{name}' for name in immutable)
    conditions += " OR (OLD.device_id IS NOT NULL AND NEW.device_id IS NOT OLD.device_id)"
    conditions += " OR (OLD.send_state='received' AND (NEW.send_state IS NOT OLD.send_state OR NEW.receipt_json IS NOT OLD.receipt_json))"
    op.execute(f"CREATE TRIGGER diagnostic_runs_immutable BEFORE UPDATE ON deployment_diagnostic_runs WHEN {conditions} BEGIN SELECT RAISE(ABORT, 'diagnostic identity is immutable'); END")


def downgrade():
    raise RuntimeError('請以匹配 image/schema 的備份還原至新目標，保留檢查報告與故障庫')
