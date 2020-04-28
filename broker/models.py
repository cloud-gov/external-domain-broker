from openbrokerapi.service_broker import OperationState

from . import db
from .tasks import create_le_user


class Base(db.Model):
    __abstract__ = True

    created_at = db.Column(db.TIMESTAMP(timezone=True), server_default=db.func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), onupdate=db.func.now())


class ACMEUser(Base):
    __tablename__ = "acme_user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, nullable=False)
    uri = db.Column(db.String, nullable=False)
    private_key = db.Column(db.Text, nullable=False)
    registration_json = db.Column(db.Text)
    service_instances = db.relation(
        "ServiceInstance", backref="acme_user", lazy="dynamic"
    )


class ServiceInstance(Base):
    id = db.Column(db.String(36), primary_key=True)
    operations = db.relation("Operation", backref="service_instance", lazy="dynamic")
    acme_user_id = db.Column(db.Integer, db.ForeignKey("acme_user.id"))

    def __repr__(self):
        return f"<ServiceInstance {self.id}>"


class Operation(Base):
    id = db.Column(db.Integer, primary_key=True)
    service_instance_id = db.Column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    state = db.Column(db.Enum(OperationState), nullable=False)

    def __repr__(self):
        return f"<Operation {self.id} {self.state}>"

    def queue_tasks(self):
        create_le_user(self.id)
