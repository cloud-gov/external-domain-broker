"""change_shield_associated_health_check_field

Revision ID: 819e31a29986
Revises: 7641f0967110
Create Date: 2024-08-28 21:39:29.286173

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "819e31a29986"
down_revision = "7641f0967110"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "shield_associated_health_check",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            )
        )
        batch_op.drop_column("shield_associated_health_checks")

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "shield_associated_health_checks",
                postgresql.JSONB(astext_type=sa.Text()),
                autoincrement=False,
                nullable=True,
            )
        )
        batch_op.drop_column("shield_associated_health_check")

    # ### end Alembic commands ###