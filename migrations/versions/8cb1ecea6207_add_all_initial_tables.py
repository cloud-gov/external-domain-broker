"""add all initial tables

Revision ID: 8cb1ecea6207
Revises:
Create Date: 2020-06-04 20:51:39.664779

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "8cb1ecea6207"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "acme_user",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("uri", sa.String(), nullable=False),
        sa.Column(
            "private_key_pem",
            sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(),
            nullable=False,
        ),
        sa.Column("registration_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "service_instance",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("acme_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "domain_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("order_json", sa.Text(), nullable=True),
        sa.Column("csr_pem", sa.Text(), nullable=True),
        sa.Column("cert_pem", sa.Text(), nullable=True),
        sa.Column(
            "private_key_pem",
            sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(),
            nullable=True,
        ),
        sa.Column("fullchain_pem", sa.Text(), nullable=True),
        sa.Column("iam_server_certificate_id", sa.String(), nullable=True),
        sa.Column("iam_server_certificate_name", sa.String(), nullable=True),
        sa.Column("iam_server_certificate_arn", sa.String(), nullable=True),
        sa.Column("cloudfront_distribution_arn", sa.String(), nullable=True),
        sa.Column("cloudfront_distribution_id", sa.String(), nullable=True),
        sa.Column("cloudfront_distribution_url", sa.String(), nullable=True),
        sa.Column("cloudfront_origin_hostname", sa.String(), nullable=True),
        sa.Column("cloudfront_origin_path", sa.String(), nullable=True),
        sa.Column(
            "route53_change_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("deactivated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["acme_user_id"], ["acme_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "challenge",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_instance_id", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("validation_domain", sa.String(), nullable=False),
        sa.Column("validation_contents", sa.Text(), nullable=False),
        sa.Column("body_json", sa.Text(), nullable=True),
        sa.Column("answered", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["service_instance_id"], ["service_instance.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "operation",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_instance_id", sa.String(), nullable=False),
        sa.Column("state", sa.String(), server_default="in progress", nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["service_instance_id"], ["service_instance.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("operation")
    op.drop_table("challenge")
    op.drop_table("service_instance")
    op.drop_table("acme_user")
    # ### end Alembic commands ###
