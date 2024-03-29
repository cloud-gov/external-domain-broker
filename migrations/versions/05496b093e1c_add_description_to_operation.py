"""add description to Operation

Revision ID: 05496b093e1c
Revises: 7b5e889e7328
Create Date: 2020-06-22 18:39:19.871827

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = "05496b093e1c"
down_revision = "7b5e889e7328"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "operation", sa.Column("step_description", sa.String(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("operation", "step_description")
    # ### end Alembic commands ###
