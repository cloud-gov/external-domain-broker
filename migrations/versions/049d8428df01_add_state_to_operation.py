"""add state to operation

Revision ID: 049d8428df01
Revises: cbb0b5789fa6
Create Date: 2020-05-31 21:30:17.745349

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "049d8428df01"
down_revision = "cbb0b5789fa6"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("operation", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "state",
                sa.Enum("in progress", "succeeded", "failed", name="operationstate"),
                server_default="in progress",
                nullable=False,
            )
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("operation", schema=None) as batch_op:
        batch_op.drop_column("state")

    # ### end Alembic commands ###
