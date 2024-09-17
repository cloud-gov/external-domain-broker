from enum import Enum
from typing import List
import logging


from sqlalchemy.dialects import postgresql
import sqlalchemy as sa
from sqlalchemy.orm import mapped_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy_utils.types.encrypted.encrypted_type import (
    AesGcmEngine,
    StringEncryptedType,
)
from openbrokerapi.service_broker import OperationState

from broker.extensions import config, db


logger = logging.getLogger(__name__)


class ServiceInstanceTypes(Enum):
    ALB = "alb_service_instance"
    CDN = "cdn_service_instance"
    CDN_DEDICATED_WAF = "cdn_dedicated_waf_service_instance"
    DEDICATED_ALB = "dedicated_alb_service_instance"
    MIGRATION = "migration_service_instance"


def db_encryption_key():
    return config.DATABASE_ENCRYPTION_KEY


class Base(db.Model):
    __abstract__ = True

    created_at = mapped_column(
        db.TIMESTAMP(timezone=True), server_default=db.func.now()
    )
    updated_at = mapped_column(db.TIMESTAMP(timezone=True), onupdate=db.func.now())


class ACMEUser(Base):
    __tablename__ = "acme_user"

    id = mapped_column(db.Integer, primary_key=True)
    email = mapped_column(db.String, nullable=False)
    uri = mapped_column(db.String, nullable=False)
    private_key_pem = mapped_column(
        StringEncryptedType(db.Text, db_encryption_key, AesGcmEngine, "pkcs5"),
        nullable=False,
    )

    registration_json = mapped_column(db.Text)
    service_instances = db.relation(
        "ServiceInstance", backref="acme_user", lazy="dynamic"
    )


class Certificate(Base):
    __tablename__ = "certificate"
    id = mapped_column(db.Integer, primary_key=True)
    service_instance_id = mapped_column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    subject_alternative_names = mapped_column(postgresql.JSONB, default=[])
    leaf_pem = mapped_column(db.Text)
    expires_at = mapped_column(db.TIMESTAMP(timezone=True))
    private_key_pem = mapped_column(
        StringEncryptedType(db.Text, db_encryption_key, AesGcmEngine, "pkcs5")
    )
    csr_pem = mapped_column(db.Text)
    fullchain_pem = mapped_column(db.Text)
    iam_server_certificate_id = mapped_column(db.String)
    iam_server_certificate_name = mapped_column(db.String)
    iam_server_certificate_arn = mapped_column(db.String)
    challenges = db.relation(
        "Challenge", backref="certificate", lazy="dynamic", cascade="all, delete-orphan"
    )
    order_json = mapped_column(db.Text)


class ServiceInstance(Base):
    __tablename__ = "service_instance"
    id = mapped_column(db.String(36), primary_key=True)
    operations = db.relation("Operation", backref="service_instance", lazy="dynamic")
    acme_user_id = mapped_column(db.Integer, db.ForeignKey("acme_user.id"))
    domain_names = mapped_column(postgresql.JSONB, default=[])
    instance_type = mapped_column(db.Text)

    domain_internal = mapped_column(db.String)

    route53_alias_hosted_zone = mapped_column(db.String)
    route53_change_ids = mapped_column(postgresql.JSONB, default=[])

    deactivated_at = mapped_column(db.TIMESTAMP(timezone=True))
    certificates = db.relation(
        "Certificate",
        backref="service_instance",
        foreign_keys=Certificate.service_instance_id,
    )
    current_certificate_id = mapped_column(
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
    new_certificate_id = mapped_column(
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

    tags = mapped_column(postgresql.JSONB)

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
        return type(self) is new_type or new_type in self.update_targets()

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

    cloudfront_distribution_arn = mapped_column(db.String)
    cloudfront_distribution_id = mapped_column(db.String)
    cloudfront_origin_hostname = mapped_column(db.String)
    cloudfront_origin_path = mapped_column(db.String)
    forward_cookie_policy = mapped_column(
        db.String, default=ForwardCookiePolicy.ALL.value
    )
    forwarded_cookies = mapped_column(postgresql.JSONB, default=[])
    forwarded_headers = mapped_column(postgresql.JSONB, default=[])
    error_responses = mapped_column(postgresql.JSONB, default=[])
    origin_protocol_policy = mapped_column(db.String)

    __mapper_args__ = {"polymorphic_identity": ServiceInstanceTypes.CDN.value}

    @classmethod
    def update_targets(self) -> List[type]:
        return [CDNServiceInstance, CDNDedicatedWAFServiceInstance]

    def __repr__(self):
        return f"<CDNServiceInstance {self.id} {self.domain_names}>"


class CDNDedicatedWAFServiceInstance(CDNServiceInstance):
    dedicated_waf_web_acl_arn = mapped_column(db.String)
    dedicated_waf_web_acl_id = mapped_column(db.String)
    dedicated_waf_web_acl_name = mapped_column(db.String)
    route53_health_checks = mapped_column(postgresql.JSONB, default=[])
    shield_associated_health_check = mapped_column(postgresql.JSONB, default={})
    cloudwatch_health_check_alarms = mapped_column(postgresql.JSONB, default=[])
    alarm_notification_email = mapped_column(db.String, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": ServiceInstanceTypes.CDN_DEDICATED_WAF.value
    }

    def __repr__(self):
        return f"<CDNDedicatedWAFServiceInstance {self.id} {self.domain_names}>"


class AbstractALBServiceInstance(ServiceInstance):
    """
    This allows us to have ALBServiceInstance and
    DedicatedALBServiceInstance share columns without
    making one an instance of the other.
    """

    __abstract__ = True
    alb_arn = mapped_column(db.String, use_existing_column=True)
    alb_listener_arn = mapped_column(db.String, use_existing_column=True)

    previous_alb_arn = mapped_column(db.String, use_existing_column=True)
    previous_alb_listener_arn = mapped_column(db.String, use_existing_column=True)


class ALBServiceInstance(AbstractALBServiceInstance):

    __mapper_args__ = {"polymorphic_identity": ServiceInstanceTypes.ALB.value}

    @classmethod
    def update_targets(self) -> List[type]:
        return [ALBServiceInstance, DedicatedALBServiceInstance]

    def __repr__(self):
        return f"<ALBServiceInstance {self.id} {self.domain_names}>"


class DedicatedALBServiceInstance(AbstractALBServiceInstance):
    org_id = mapped_column(db.String)

    __mapper_args__ = {"polymorphic_identity": ServiceInstanceTypes.DEDICATED_ALB.value}

    @classmethod
    def update_targets(self) -> List[type]:
        return [DedicatedALBServiceInstance]

    def __repr__(self):
        return f"<DedicatedALBServiceInstance {self.id} {self.domain_names}>"


class MigrationServiceInstance(ServiceInstance):
    __mapper_args__ = {"polymorphic_identity": ServiceInstanceTypes.MIGRATION.value}

    @classmethod
    def update_targets(self) -> List[type]:
        return [ALBServiceInstance, CDNServiceInstance]

    def __repr__(self):
        return f"<MigrationServiceInstance {self.id} {self.domain_names}>"


class Operation(Base):
    __tablename__ = "operation"
    # operation.state = Operation.States.IN_PROGRESS.value
    States = OperationState

    # operation.action = Operation.Actions.PROVISION.value
    class Actions(Enum):
        PROVISION = "Provision"
        DEPROVISION = "Deprovision"
        RENEW = "Renew"
        UPDATE = "Update"
        MIGRATE_TO_BROKER = "Migrate to broker"

    id = mapped_column(db.Integer, primary_key=True)
    service_instance_id = mapped_column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    state = mapped_column(
        db.String,
        default=States.IN_PROGRESS.value,
        server_default=States.IN_PROGRESS.value,
        nullable=False,
    )
    action = mapped_column(db.String, nullable=False)
    canceled_at = mapped_column(db.TIMESTAMP(timezone=True))
    step_description = mapped_column(db.String)

    def __repr__(self):
        return f"<Operation {self.id} {self.state}>"


class Challenge(Base):
    __tablename__ = "challenge"
    id = mapped_column(db.Integer, primary_key=True)
    certificate_id = mapped_column(
        db.Integer, db.ForeignKey("certificate.id"), nullable=False
    )
    domain = mapped_column(db.String, nullable=False)
    validation_domain = mapped_column(db.String, nullable=False)
    validation_contents = mapped_column(db.Text, nullable=False)
    body_json = mapped_column(db.Text)
    answered = mapped_column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Challenge {self.id} {self.domain}>"


class DedicatedALBListener(Base):
    __tablename__ = "dedicated_alb_listener"
    id = mapped_column(db.Integer, primary_key=True)
    listener_arn = mapped_column(db.String, nullable=False, unique=True)
    alb_arn = mapped_column(db.String, nullable=True)
    dedicated_org = mapped_column(db.String, nullable=True)

    @classmethod
    def load_albs(cls, listener_arns: list[str]):
        logger.info(f"Starting load_albs with {listener_arns}")
        if listener_arns:
            logger.info(f"Loading dedicated albs {listener_arns}")
            stmt = insert(DedicatedALBListener).values(
                [dict(listener_arn=arn) for arn in listener_arns]
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["listener_arn"])
            db.session.execute(stmt)
            db.session.commit()


def change_instance_type(
    service_instance: ServiceInstance, new_type: type, session
) -> ServiceInstance:
    """
    Convert `service_instance` to `new_type` and return the converted instance
    """
    if type(service_instance) is new_type:
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
    service_instance = db.session.get(new_type, id_)
    return service_instance
