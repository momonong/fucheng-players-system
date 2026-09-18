"""Anonymous name-selection registration and honest public actor provenance."""
from alembic import op
import sqlalchemy as sa

revision = '0003_public_registration'
down_revision = '0002_competition_registration'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('public_visits',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('csrf_token', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_public_visits_expires_at', 'public_visits', ['expires_at'])
    op.create_table('auth_attempts',
        sa.Column('key_hash', sa.String(64), primary_key=True),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('window_start', sa.DateTime(), nullable=False))
    op.create_index('ix_auth_attempts_window_start', 'auth_attempts', ['window_start'])
    for table in ('competition_registrations', 'registration_audits'):
        with op.batch_alter_table(table) as batch:
            prefixes = ('created_by', 'updated_by') if table == 'competition_registrations' else ('actor',)
            for prefix in prefixes:
                admin = f'{prefix}_admin_id' if prefix != 'actor' else 'admin_id'
                visit, kind = f'{prefix}_visit_id', f'{prefix}_kind'
                batch.alter_column(admin, existing_type=sa.String(36), nullable=True)
                batch.add_column(sa.Column(kind, sa.String(10), nullable=False, server_default='admin'))
                batch.add_column(sa.Column(visit, sa.String(36), nullable=True))
                batch.create_foreign_key(f'fk_{table}_{visit}', 'public_visits', [visit], ['id'], ondelete='RESTRICT')
                batch.create_check_constraint(f'ck_{prefix}_exclusive_actor',
                    f"({kind}='admin' AND {admin} IS NOT NULL AND {visit} IS NULL) OR "
                    f"({kind}='public' AND {admin} IS NULL AND {visit} IS NOT NULL) OR "
                    f"({kind}='system' AND {admin} IS NULL AND {visit} IS NULL)")
            if table == 'registration_audits':
                batch.add_column(sa.Column('request_fingerprint', sa.String(64), nullable=True))


def downgrade():
    raise RuntimeError('免登入報名含新的稽核來源；請以升級前備份還原至新路徑，不執行破壞性降版')
