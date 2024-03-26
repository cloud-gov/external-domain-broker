"""add listener arn to alb service instance

Revision ID: 6aeacb57a929
Revises: 45288546dc63
Create Date: 2020-06-18 18:37:07.991155

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = "6aeacb57a929"
down_revision = "45288546dc63"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "service_instance", sa.Column("alb_listener_arn", sa.String(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("service_instance", "alb_listener_arn")
    # ### end Alembic commands ###
