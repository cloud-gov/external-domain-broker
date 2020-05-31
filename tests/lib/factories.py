from factory import Sequence, SubFactory, LazyAttribute
from factory.alchemy import SQLAlchemyModelFactory

from broker.extensions import db
from broker.models import Operation, ServiceInstance, ACMEUser, Challenge


class BaseFactory(SQLAlchemyModelFactory):
    class Meta(object):
        sqlalchemy_session = db.session  # the SQLAlchemy session object
        sqlalchemy_session_persistence = "flush"


class ServiceInstanceFactory(BaseFactory):
    class Meta(object):
        model = ServiceInstance

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

    state = Operation.States.IN_PROGRESS
    action = Operation.Actions.PROVISION
    service_instance = SubFactory(ServiceInstanceFactory)


class ChallengeFactory(BaseFactory):
    class Meta(object):
        model = Challenge

    id = Sequence(int)
    domain = "some.domain.com"
    validation_domain = LazyAttribute(lambda obj: f"_acme-challenge.{obj.domain}")
    validation_contents = LazyAttribute(lambda obj: f"{obj.domain} response")
