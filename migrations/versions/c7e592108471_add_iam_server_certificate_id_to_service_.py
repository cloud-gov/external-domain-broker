"""add iam_server_certificate_id to service instance

Revision ID: c7e592108471
Revises: e4e202fc7541
Create Date: 2020-05-22 17:20:07.344478

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c7e592108471"
down_revision = "e4e202fc7541"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("iam_server_certificate_id", sa.String(), nullable=True)
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.drop_column("iam_server_certificate_id")
