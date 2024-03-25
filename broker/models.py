from enum import Enum
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa

from typing import List

from openbrokerapi.service_broker import OperationState
from sqlalchemy_utils.types.encrypted.encrypted_type import (
    AesGcmEngine,
    StringEncryptedType,
)

from broker.extensions import config, db


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


class Certificate(Base):
    id = db.Column(db.Integer, primary_key=True)
    service_instance_id = db.Column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    subject_alternative_names = db.Column(postgresql.JSONB, default=[])
    leaf_pem = db.Column(db.Text)
    expires_at = db.Column(db.TIMESTAMP(timezone=True))
    private_key_pem = db.Column(
        StringEncryptedType(db.Text, db_encryption_key, AesGcmEngine, "pkcs5")
    )
    csr_pem = db.Column(db.Text)
    fullchain_pem = db.Column(db.Text)
    iam_server_certificate_id = db.Column(db.String)
    iam_server_certificate_name = db.Column(db.String)
    iam_server_certificate_arn = db.Column(db.String)
    challenges = db.relation(
        "Challenge", backref="certificate", lazy="dynamic", cascade="all, delete-orphan"
    )
    order_json = db.Column(db.Text)


class ServiceInstance(Base):
    __tablename__ = "service_instance"
    id = db.Column(db.String(36), primary_key=True)
    operations = db.relation("Operation", backref="service_instance", lazy="dynamic")
    acme_user_id = db.Column(db.Integer, db.ForeignKey("acme_user.id"))
    domain_names = db.Column(postgresql.JSONB, default=[])
    instance_type = db.Column(db.Text)

    domain_internal = db.Column(db.String)

    route53_alias_hosted_zone = db.Column(db.String)
    route53_change_ids = db.Column(postgresql.JSONB, default=[])

    deactivated_at = db.Column(db.TIMESTAMP(timezone=True))
    certificates = db.relation(
        "Certificate",
        backref="service_instance",
        foreign_keys=Certificate.service_instance_id,
    )
    current_certificate_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "certificate.id",
            name="fk__service_instance__certificate__current_certificate_id",
        ),
    )
    current_certificate = db.relation(
        Certificate,
        primaryjoin=current_certificate_id == Certificate.id,
        foreign_keys=current_certificate_id,
        post_update=True,
    )
    new_certificate_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "certificate.id",
            name="fk__service_instance__certificate__new_certificate_id",
        ),
    )
    new_certificate = db.relation(
        Certificate,
        primaryjoin=new_certificate_id == Certificate.id,
        foreign_keys=new_certificate_id,
        post_update=True,
    )

    __mapper_args__ = {
        "polymorphic_identity": "service_instance",
        "polymorphic_on": instance_type,
    }

    def has_active_operations(self):
        for operation in self.operations:
            if (
                operation.state == Operation.States.IN_PROGRESS.value
                and operation.canceled_at is None
            ):
                return True
        return False

    def can_update_to_type(self, new_type) -> bool:
        return type(self) == new_type or new_type in self.update_targets()

    @classmethod
    def update_targets(self) -> List[type]:
        return []

    def __repr__(self):
        return f"<ServiceInstance {self.id} {self.domain_names}>"


class CDNServiceInstance(ServiceInstance):
    class ForwardCookiePolicy(Enum):
        ALL = "all"
        NONE = "none"
        WHITELIST = "whitelist"

    class ProtocolPolicy(Enum):
        HTTPS = "https-only"
        HTTP = "http-only"

    cloudfront_distribution_arn = db.Column(db.String)
    cloudfront_distribution_id = db.Column(db.String)
    cloudfront_origin_hostname = db.Column(db.String)
    cloudfront_origin_path = db.Column(db.String)
    forward_cookie_policy = db.Column(db.String, default=ForwardCookiePolicy.ALL.value)
    forwarded_cookies = db.Column(postgresql.JSONB, default=[])
    forwarded_headers = db.Column(postgresql.JSONB, default=[])
    error_responses = db.Column(postgresql.JSONB, default=[])
    origin_protocol_policy = db.Column(db.String)

    __mapper_args__ = {"polymorphic_identity": "cdn_service_instance"}

    def __repr__(self):
        return f"<CDNServiceInstance {self.id} {self.domain_names}>"


class AbstractALBServiceInstance(ServiceInstance):
    """
    This allows us to have ALBServiceInstance and
    DedicatedALBServiceInstance share columns without
    making one an instance of the other.
    """

    alb_arn = db.Column(db.String)
    alb_listener_arn = db.Column(db.String)

    previous_alb_arn = db.Column(db.String)
    previous_alb_listener_arn = db.Column(db.String)


class ALBServiceInstance(AbstractALBServiceInstance):

    __mapper_args__ = {"polymorphic_identity": "alb_service_instance"}

    @classmethod
    def update_targets(self) -> List[type]:
        return [ALBServiceInstance, DedicatedALBServiceInstance]

    def __repr__(self):
        return f"<ALBServiceInstance {self.id} {self.domain_names}>"


class DedicatedALBServiceInstance(AbstractALBServiceInstance):
    org_id = db.Column(db.String)

    __mapper_args__ = {"polymorphic_identity": "dedicated_alb_service_instance"}

    @classmethod
    def update_targets(self) -> List[type]:
        return [DedicatedALBServiceInstance]

    def __repr__(self):
        return f"<DedicatedALBServiceInstance {self.id} {self.domain_names}>"


class MigrationServiceInstance(ServiceInstance):
    __mapper_args__ = {"polymorphic_identity": "migration_service_instance"}

    @classmethod
    def update_targets(self) -> List[type]:
        return [ALBServiceInstance, CDNServiceInstance]

    def __repr__(self):
        return f"<MigrationServiceInstance {self.id} {self.domain_names}>"


class Operation(Base):
    # operation.state = Operation.States.IN_PROGRESS.value
    States = OperationState

    # operation.action = Operation.Actions.PROVISION.value
    class Actions(Enum):
        PROVISION = "Provision"
        DEPROVISION = "Deprovision"
        RENEW = "Renew"
        UPDATE = "Update"
        MIGRATE_TO_BROKER = "Migrate to broker"

    id = db.Column(db.Integer, primary_key=True)
    service_instance_id = db.Column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    state = db.Column(
        db.String,
        default=States.IN_PROGRESS.value,
        server_default=States.IN_PROGRESS.value,
        nullable=False,
    )
    action = db.Column(db.String, nullable=False)
    canceled_at = db.Column(db.TIMESTAMP(timezone=True))
    step_description = db.Column(db.String)

    def __repr__(self):
        return f"<Operation {self.id} {self.state}>"


class Challenge(Base):
    id = db.Column(db.Integer, primary_key=True)
    certificate_id = db.Column(
        db.Integer, db.ForeignKey("certificate.id"), nullable=False
    )
    domain = db.Column(db.String, nullable=False)
    validation_domain = db.Column(db.String, nullable=False)
    validation_contents = db.Column(db.Text, nullable=False)
    body_json = db.Column(db.Text)
    answered = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Challenge {self.id} {self.domain}>"


class DedicatedALBListener(Base):
    id = db.Column(db.Integer, primary_key=True)
    listener_arn = db.Column(db.String, nullable=False, unique=True)
    alb_arn = db.Column(db.String, nullable=True)
    dedicated_org = db.Column(db.String, nullable=True)


def change_instance_type(
    service_instance: ServiceInstance, new_type: type, session
) -> ServiceInstance:
    """
    Convert `service_instance` to `new_type` and return the converted instance
    """
    if type(service_instance) == new_type:
        return service_instance
    if not service_instance.can_update_to_type(new_type):
        raise NotImplementedError()
    new_type_identity = new_type.__mapper_args__["polymorphic_identity"]
    id_ = service_instance.id
    # we need to use raw sql here because SqlAlchemy doesn't support changing types
    # cloning would probably also work, but keeping track of the certificates gets fiddly
    t = sa.text(
        "UPDATE service_instance SET instance_type = :type_id WHERE id = :instance_id"
    ).bindparams(instance_id=id_, type_id=new_type_identity)
    session.execute(t)
    session.expunge_all()
    service_instance = new_type.query.get(id_)
    return service_instance
