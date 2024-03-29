"""add challenges to certificate

Revision ID: 85cc14440898
Revises: 18f343c889ec
Create Date: 2020-07-30 22:55:57.885486

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = "85cc14440898"
down_revision = "18f343c889ec"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("challenge", sa.Column("certificate_id", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "challenge", "certificate", ["certificate_id"], ["id"])
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, "challenge", type_="foreignkey")
    op.drop_column("challenge", "certificate_id")
    # ### end Alembic commands ###
