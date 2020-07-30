"""add order_json to certificate

Revision ID: 395d9a0460cb
Revises: 85cc14440898
Create Date: 2020-07-30 23:15:43.355099

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = "395d9a0460cb"
down_revision = "85cc14440898"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("certificate", sa.Column("order_json", sa.Text(), nullable=True))
    op.alter_column(
        "challenge", "certificate_id", existing_type=sa.INTEGER(), nullable=True
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "challenge", "certificate_id", existing_type=sa.INTEGER(), nullable=False
    )
    op.drop_column("certificate", "order_json")
    # ### end Alembic commands ###
