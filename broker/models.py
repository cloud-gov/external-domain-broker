from openbrokerapi.service_broker import OperationState

from . import db
from .tasks import queue_all_provision_tasks_for_operation


class Base(db.Model):
    __abstract__ = True

    created_at = db.Column(db.TIMESTAMP(timezone=True), server_default=db.func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), onupdate=db.func.now())


class ACMEUser(Base):
    __tablename__ = "acme_user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, nullable=False)
    uri = db.Column(db.String, nullable=False)
    private_key_pem = db.Column(db.Text, nullable=False)
    registration_json = db.Column(db.Text)
    service_instances = db.relation(
        "ServiceInstance", backref="acme_user", lazy="dynamic"
    )


class ServiceInstance(Base):
    id = db.Column(db.String(36), primary_key=True)
    operations = db.relation("Operation", backref="service_instance", lazy="dynamic")
    challenges = db.relation("Challenge", backref="service_instance", lazy="dynamic")
    acme_user_id = db.Column(db.Integer, db.ForeignKey("acme_user.id"))
    domain_names = db.Column(db.JSON, default=[])
    order_json = db.Column(db.Text)

    csr_pem = db.Column(db.Text)
    cert_pem = db.Column(db.Text)
    private_key_pem = db.Column(db.Text)
    fullchain_pem = db.Column(db.Text)

    iam_server_certificate_id = db.Column(db.String)
    iam_server_certificate_arn = db.Column(db.String)

    def __repr__(self):
        return f"<ServiceInstance {self.id} {self.domain_names}>"


class Operation(Base):
    id = db.Column(db.Integer, primary_key=True)
    service_instance_id = db.Column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    state = db.Column(db.Enum(OperationState), nullable=False)

    def __repr__(self):
        return f"<Operation {self.id} {self.state}>"

    def queue_tasks(self):
        queue_all_provision_tasks_for_operation(self.id)


class Challenge(Base):
    id = db.Column(db.Integer, primary_key=True)
    service_instance_id = db.Column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    domain = db.Column(db.String, nullable=False)
    validation_domain = db.Column(db.String, nullable=False)
    validation_contents = db.Column(db.Text, nullable=False)
    body_json = db.Column(db.Text)

    def __repr__(self):
        return f"<Challenge {self.id} {self.domain}>"
