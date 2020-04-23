from . import db


class TimestampMixin(object):
    created_at = db.Column(db.TIMESTAMP(timezone=True), server_default=db.func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), onupdate=db.func.now())


class ServiceInstance(db.Model, TimestampMixin):
    id = db.Column(db.String(36), primary_key=True)
    status = db.Column(db.Text, nullable=False)
