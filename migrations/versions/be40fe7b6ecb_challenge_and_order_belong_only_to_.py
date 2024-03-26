"""challenge and order belong only to certificate

Revision ID: be40fe7b6ecb
Revises: 395d9a0460cb
Create Date: 2020-07-31 18:13:45.886519

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
import sqlalchemy_utils
from sqlalchemy.dialects import postgresql
from sqlalchemy_utils.types.encrypted.encrypted_type import (
    AesGcmEngine,
    StringEncryptedType,
)
from sqlalchemy.orm import declarative_base

from broker.config import config_from_env

# revision identifiers, used by Alembic.
revision = "be40fe7b6ecb"
down_revision = "395d9a0460cb"
branch_labels = None
depends_on = None


Base = declarative_base()


class Certificate(Base):
    __tablename__ = "certificate"
    id = sa.Column(sa.Integer, primary_key=True)
    service_instance_id = sa.Column(
        sa.String, sa.ForeignKey("service_instance.id"), nullable=False
    )


class ServiceInstance(Base):
    __tablename__ = "service_instance"
    id = sa.Column(sa.String(36), primary_key=True)
    current_certificate_id = sa.Column(sa.Integer, sa.ForeignKey("certificate.id"))
    new_certificate_id = sa.Column(sa.Integer, sa.ForeignKey("certificate.id"))


class Challenge(Base):
    __tablename__ = "challenge"
    id = sa.Column(sa.Integer, primary_key=True)
    service_instance_id = sa.Column(
        sa.String, sa.ForeignKey("service_instance.id"), nullable=False
    )
    certificate_id = sa.Column(
        sa.Integer, sa.ForeignKey("certificate.id"), nullable=True
    )


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    bind = op.get_bind()
    session = orm.Session(bind=bind)
    for challenge in session.query(Challenge):
        if challenge.certificate_id is None:
            service_instance = session.query(ServiceInstance).get(
                challenge.service_instance_id
            )
            if service_instance.new_certificate_id is not None:
                challenge.certificate_id = service_instance.new_certificate_id
            else:
                challenge.certificate_id = service_instance.current_certificate_id
            session.add(challenge)
    session.commit()

    op.alter_column(
        "challenge", "certificate_id", existing_type=sa.INTEGER(), nullable=False
    )
    op.drop_constraint(
        "challenge_service_instance_id_fkey", "challenge", type_="foreignkey"
    )
    op.drop_column("challenge", "service_instance_id")
    op.drop_column("service_instance", "order_json")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "service_instance",
        sa.Column("order_json", sa.TEXT(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "challenge",
        sa.Column(
            "service_instance_id", sa.VARCHAR(), autoincrement=False, nullable=False
        ),
    )
    op.create_foreign_key(
        "challenge_service_instance_id_fkey",
        "challenge",
        "service_instance",
        ["service_instance_id"],
        ["id"],
    )
    op.alter_column(
        "challenge", "certificate_id", existing_type=sa.INTEGER(), nullable=True
    )
    # ### end Alembic commands ###
