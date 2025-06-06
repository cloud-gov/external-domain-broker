"""add cache_policy_id and origin_request_policy_id

Revision ID: f411b8287906
Revises: 9d0581fefff2
Create Date: 2025-04-24 15:03:19.680777

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f411b8287906"
down_revision = "9d0581fefff2"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cache_policy_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("origin_request_policy_id", sa.String(), nullable=True)
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.drop_column("origin_request_policy_id")
        batch_op.drop_column("cache_policy_id")

    # ### end Alembic commands ###
