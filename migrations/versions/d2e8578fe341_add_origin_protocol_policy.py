"""add origin-protocol-policy

Revision ID: d2e8578fe341
Revises: e7fe4c0162f9
Create Date: 2020-06-30 00:46:53.784035

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = "d2e8578fe341"
down_revision = "e7fe4c0162f9"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "service_instance",
        sa.Column("origin_protocol_policy", sa.String(), nullable=True),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("service_instance", "origin_protocol_policy")
    # ### end Alembic commands ###
