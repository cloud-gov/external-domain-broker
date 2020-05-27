"""add cloudfront distribution url to service instance

Revision ID: 1ebd34d71844
Revises: f9d6018a855d
Create Date: 2020-05-28 20:42:41.401593

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1ebd34d71844'
down_revision = 'f9d6018a855d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('service_instance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cloudfront_distribution_url', sa.String(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('service_instance', schema=None) as batch_op:
        batch_op.drop_column('cloudfront_distribution_url')

    # ### end Alembic commands ###
