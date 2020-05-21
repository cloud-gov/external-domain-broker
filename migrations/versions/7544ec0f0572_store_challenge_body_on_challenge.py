"""Store challenge body on Challenge

Revision ID: 7544ec0f0572
Revises: 12607233c729
Create Date: 2020-05-20 16:47:22.776638

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7544ec0f0572"
down_revision = "12607233c729"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("challenge", schema=None) as batch_op:
        batch_op.add_column(sa.Column("body_json", sa.Text(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("challenge", schema=None) as batch_op:
        batch_op.drop_column("body_json")

    # ### end Alembic commands ###
