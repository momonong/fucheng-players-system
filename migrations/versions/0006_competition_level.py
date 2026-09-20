"""Independent per-registration competition level, initialized from its own snapshot."""
from alembic import op
import sqlalchemy as sa

revision = "0006_competition_level"
down_revision = "0005_competition_deletion"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("competition_registrations", sa.Column("competition_level", sa.Integer(), nullable=True))
    op.execute("UPDATE competition_registrations SET competition_level = hard_level_snapshot")
    with op.batch_alter_table("competition_registrations") as batch:
        batch.alter_column("competition_level", existing_type=sa.Integer(), nullable=False)
        batch.create_check_constraint("ck_registration_competition_level", "competition_level BETWEEN 1 AND 10")


def downgrade():
    raise RuntimeError("當次級數與稽核不可丟棄；請使用升級前備份還原到新檔並驗證")
