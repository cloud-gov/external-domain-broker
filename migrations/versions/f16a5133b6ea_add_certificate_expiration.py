"""add certificate expiration

Revision ID: f16a5133b6ea
Revises: 05496b093e1c
Create Date: 2020-06-25 19:56:07.976236

"""
from datetime import datetime
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import declarative_base
import sqlalchemy_utils

import OpenSSL


# revision identifiers, used by Alembic.
revision = "f16a5133b6ea"
down_revision = "05496b093e1c"
branch_labels = None
depends_on = None

Base = declarative_base()


class ServiceInstance(Base):
    __tablename__ = "service_instance"
    id = sa.Column(sa.String(36), primary_key=True)
    cert_pem = sa.Column(sa.Text)
    cert_expires_at = sa.Column(sa.TIMESTAMP(timezone=True))


def upgrade():
    op.add_column(
        "service_instance",
        sa.Column("cert_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    for service_instance in session.query(ServiceInstance):
        if service_instance.cert_pem is not None:
            x509 = OpenSSL.crypto.load_certificate(
                OpenSSL.crypto.FILETYPE_PEM, service_instance.cert_pem
            )
            not_after = x509.get_notAfter().decode("utf-8")

            service_instance.cert_expires_at = datetime.strptime(
                not_after, "%Y%m%d%H%M%Sz"
            )
            session.add(service_instance)
    session.commit()


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("service_instance", "cert_expires_at")
    # ### end Alembic commands ###
