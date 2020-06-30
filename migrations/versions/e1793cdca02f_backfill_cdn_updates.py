"""backfill cdn updates

Revision ID: e1793cdca02f
Revises: d2e8578fe341
Create Date: 2020-06-30 00:53:24.426405

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e1793cdca02f"
down_revision = "d2e8578fe341"
branch_labels = None
depends_on = None

class ServiceInstance(Base):
    __tablename__ = "service_instance"
    id = sa.Column(sa.String(36), primary_key=True)
    instance_type = sa.Column(sa.String(36))
    forward_cookie_policy = sa.Column(sa.String)
    forwarded_headers = sa.Column(postgresql.JSONB)
    origin_protocol_policy = sa.Column(sa.String)


def upgrade():
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    for service_instance in session.query(ServiceInstance):
        if service_instance.instance_type == "cdn_service_instance":
            service_instance.origin_protocol_policy = 'https-only'
            service_instance.forwarded_headers = ['HOST']
            session.add(service_instance)
    session.commit()


def downgrade():
    pass
