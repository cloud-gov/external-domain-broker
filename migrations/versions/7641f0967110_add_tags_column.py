"""add_tags_column

Revision ID: 7641f0967110
Revises: 504d3d141b25
Create Date: 2024-08-20 21:37:26.698389

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "7641f0967110"
down_revision = "504d3d141b25"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.drop_column("tags")

    # ### end Alembic commands ###
