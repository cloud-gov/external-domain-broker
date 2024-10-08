"""add_cloudwatch_health_check_alarms

Revision ID: 4c57fe392f3c
Revises: 819e31a29986
Create Date: 2024-09-04 14:52:36.703601

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "4c57fe392f3c"
down_revision = "819e31a29986"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "cloudwatch_health_check_alarms",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            )
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.drop_column("cloudwatch_health_check_alarms")

    # ### end Alembic commands ###
