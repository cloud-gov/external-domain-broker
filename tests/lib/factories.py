from factory import LazyAttribute, Sequence, SubFactory
from factory.alchemy import SQLAlchemyModelFactory

from broker.extensions import db
from broker.models import (
    ACMEUser,
    Certificate,
    Challenge,
    Operation,
    CDNServiceInstance,
    ALBServiceInstance,
)


class BaseFactory(SQLAlchemyModelFactory):
    class Meta(object):
        sqlalchemy_session = db.session  # the SQLAlchemy session object
        sqlalchemy_session_persistence = "flush"


class CDNServiceInstanceFactory(BaseFactory):
    class Meta(object):
        model = CDNServiceInstance

    id = Sequence(lambda n: "UUID {}".format(n))


class ALBServiceInstanceFactory(BaseFactory):
    class Meta(object):
        model = ALBServiceInstance

    id = Sequence(lambda n: "UUID {}".format(n))


class ACMEUserFactory(BaseFactory):
    class Meta(object):
        model = ACMEUser

    id = Sequence(int)
    email = "foo@exmple.com"
    uri = "http://exmple.com"
    private_key_pem = "PRIVATE KEY"


class OperationFactory(BaseFactory):
    class Meta(object):
        model = Operation

    state = Operation.States.IN_PROGRESS.value
    action = Operation.Actions.PROVISION.value
    service_instance = SubFactory(CDNServiceInstanceFactory)


class ChallengeFactory(BaseFactory):
    class Meta(object):
        model = Challenge

    id = Sequence(int)
    domain = "some.domain.com"
    validation_domain = LazyAttribute(lambda obj: f"_acme-challenge.{obj.domain}")
    validation_contents = LazyAttribute(lambda obj: f"{obj.domain} response")


class CertificateFactory(BaseFactory):
    class Meta(object):
        model = Certificate

    id = Sequence(int)
