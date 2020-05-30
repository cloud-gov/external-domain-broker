from openbrokerapi.service_broker import OperationState
from sqlalchemy_utils.types.encrypted.encrypted_type import (
    AesGcmEngine,
    StringEncryptedType,
)

from broker.extensions import db, config
from broker.tasks import queue_all_provision_tasks_for_operation


def db_encryption_key():
    return config.DATABASE_ENCRYPTION_KEY


class Base(db.Model):
    __abstract__ = True

    created_at = db.Column(db.TIMESTAMP(timezone=True), server_default=db.func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), onupdate=db.func.now())


class ACMEUser(Base):
    __tablename__ = "acme_user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, nullable=False)
    uri = db.Column(db.String, nullable=False)
    private_key_pem = db.Column(
        StringEncryptedType(db.Text, db_encryption_key, AesGcmEngine, "pkcs5"),
        nullable=False,
    )

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
    private_key_pem = db.Column(
        StringEncryptedType(db.Text, db_encryption_key, AesGcmEngine, "pkcs5")
    )
    fullchain_pem = db.Column(db.Text)

    iam_server_certificate_id = db.Column(db.String)
    iam_server_certificate_arn = db.Column(db.String)
    cloudfront_distribution_arn = db.Column(db.String)
    cloudfront_distribution_id = db.Column(db.String)
    cloudfront_distribution_url = db.Column(db.String)
    cloudfront_origin_hostname = db.Column(db.String)
    cloudfront_origin_path = db.Column(db.String)

    route53_change_ids = db.Column(db.JSON, default=[])

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

    States = OperationState

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
    answered = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Challenge {self.id} {self.domain}>"
