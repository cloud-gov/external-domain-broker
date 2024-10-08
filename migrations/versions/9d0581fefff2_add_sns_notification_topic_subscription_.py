"""add_sns_notification_topic_subscription_arn

Revision ID: 9d0581fefff2
Revises: e56aab1c13c0
Create Date: 2024-09-23 18:21:36.048388

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d0581fefff2"
down_revision = "e56aab1c13c0"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "sns_notification_topic_subscription_arn", sa.String(), nullable=True
            )
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.drop_column("sns_notification_topic_subscription_arn")

    # ### end Alembic commands ###
