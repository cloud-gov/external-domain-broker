"""add forwarded-headers parameter

Revision ID: e7fe4c0162f9
Revises: 68727f5db74e
Create Date: 2020-06-29 23:20:50.391452

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e7fe4c0162f9"
down_revision = "68727f5db74e"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "service_instance",
        sa.Column(
            "forwarded_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("service_instance", "forwarded_headers")
    # ### end Alembic commands ###
