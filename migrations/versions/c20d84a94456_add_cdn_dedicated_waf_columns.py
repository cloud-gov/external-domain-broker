"""add route53_health_check_ids column

Revision ID: c20d84a94456
Revises: 9a192af8c4ae
Create Date: 2024-07-02 21:14:40.468949

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c20d84a94456"
down_revision = "9a192af8c4ae"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("dedicated_waf_web_acl_arn", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "route53_health_check_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "shield_associated_health_checks",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            )
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("service_instance", schema=None) as batch_op:
        batch_op.drop_column("shield_associated_health_checks")
        batch_op.drop_column("route53_health_check_ids")
        batch_op.drop_column("dedicated_waf_web_acl_arn")

    # ### end Alembic commands ###
