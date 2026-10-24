"""Separate doubles entries, active membership, audits and immutable receipts."""
from alembic import op
import sqlalchemy as sa

revision = '0014_doubles_registration'
down_revision = '0013_announcement_deletion'
branch_labels = None
depends_on = None


def actor_check():
    return sa.CheckConstraint("(actor_kind='admin' AND admin_id IS NOT NULL AND actor_visit_id IS NULL) OR (actor_kind='public' AND admin_id IS NULL AND actor_visit_id IS NOT NULL) OR (actor_kind='system' AND admin_id IS NULL AND actor_visit_id IS NULL)", name='ck_actor_exclusive_actor')


def actor_columns():
    return [sa.Column('actor_kind',sa.String(10),nullable=False),
        sa.Column('admin_id',sa.String(36),sa.ForeignKey('admins.id',ondelete='RESTRICT')),
        sa.Column('actor_visit_id',sa.String(36),sa.ForeignKey('public_visits.id',ondelete='RESTRICT'))]


def upgrade():
    with op.batch_alter_table('competitions') as batch:
        batch.add_column(sa.Column('registration_mode',sa.String(12),nullable=False,server_default='individual'))
        batch.add_column(sa.Column('doubles_min_total_level',sa.Integer(),nullable=True))
        batch.create_check_constraint('ck_competitions_registration_mode',"registration_mode IN ('individual','doubles')")
        batch.create_check_constraint('ck_competitions_doubles_min_level','doubles_min_total_level IS NULL OR doubles_min_total_level BETWEEN 2 AND 20')
    op.create_table('doubles_entries',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('competition_id',sa.String(36),sa.ForeignKey('competitions.id',ondelete='RESTRICT'),nullable=False,index=True),
        sa.Column('status',sa.String(20),nullable=False,index=True),
        sa.Column('member_count',sa.Integer(),nullable=False),
        sa.Column('sequence',sa.Integer(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('id','competition_id',name='uq_doubles_entry_competition'),
        sa.UniqueConstraint('competition_id','sequence',name='uq_doubles_sequence'),
        sa.CheckConstraint("status IN ('waiting_partner','pending','confirmed','waitlisted','cancelled')",name='ck_doubles_status'),
        sa.CheckConstraint("member_count IN (1,2) AND (status='cancelled' OR (status='waiting_partner' AND member_count=1) OR (status IN ('pending','confirmed','waitlisted') AND member_count=2))",name='ck_doubles_member_count'),
        sa.CheckConstraint('version >= 1 AND sequence >= 1',name='ck_doubles_version_sequence'))
    op.create_table('doubles_entry_members',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('entry_id',sa.String(36),nullable=False,index=True),
        sa.Column('competition_id',sa.String(36),nullable=False,index=True),
        sa.Column('member_id',sa.String(36),sa.ForeignKey('members.id',ondelete='RESTRICT'),nullable=False,index=True),
        sa.Column('position',sa.Integer(),nullable=False),
        sa.Column('level_snapshot',sa.Integer(),nullable=False),
        sa.Column('is_active',sa.Boolean(),nullable=False),
        sa.ForeignKeyConstraint(['entry_id','competition_id'],['doubles_entries.id','doubles_entries.competition_id'],ondelete='RESTRICT'),
        sa.UniqueConstraint('entry_id','position',name='uq_doubles_member_position'),
        sa.UniqueConstraint('entry_id','member_id',name='uq_doubles_entry_member'),
        sa.CheckConstraint('position IN (1,2)',name='ck_doubles_member_position'),
        sa.CheckConstraint('level_snapshot BETWEEN 1 AND 10',name='ck_doubles_level_snapshot'))
    op.create_index('uq_doubles_active_member','doubles_entry_members',['competition_id','member_id'],unique=True,sqlite_where=sa.text('is_active=1'))
    op.create_table('doubles_audits',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('entry_id',sa.String(36),sa.ForeignKey('doubles_entries.id',ondelete='RESTRICT'),nullable=False,index=True),
        sa.Column('competition_id',sa.String(36),sa.ForeignKey('competitions.id',ondelete='RESTRICT'),nullable=False,index=True),
        *actor_columns(),
        sa.Column('action',sa.String(30),nullable=False),
        sa.Column('changes_json',sa.Text(),nullable=False),
        sa.Column('reason',sa.String(500)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,index=True),actor_check())
    op.create_table('doubles_receipts',
        sa.Column('request_id',sa.String(64),primary_key=True),
        sa.Column('competition_id',sa.String(36),sa.ForeignKey('competitions.id',ondelete='RESTRICT'),nullable=False,index=True),
        *actor_columns(),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('response_json',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),actor_check())


def downgrade():
    raise RuntimeError('請以匹配 image/schema 的備份還原至新目標，保留雙打報名、操作紀錄及故障庫')
