from openbrokerapi.service_broker import OperationState

from . import db


class TimestampMixin(object):
    created_at = db.Column(db.TIMESTAMP(timezone=True), server_default=db.func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), onupdate=db.func.now())


class ServiceInstance(db.Model, TimestampMixin):
    id = db.Column(db.String(36), primary_key=True)
    operations = db.relation("Operation", backref="service_instance", lazy="dynamic")

    def __repr__(self):
        return f"<ServiceInstance {self.id}>"


class Operation(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    service_instance_id = db.Column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    state = db.Column(db.Enum(OperationState), nullable=False)

    def __repr__(self):
        return f"<Operation {self.id} {self.state}>"
