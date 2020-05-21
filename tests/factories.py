from factory import Sequence, SubFactory
from factory.alchemy import SQLAlchemyModelFactory
from openbrokerapi.service_broker import OperationState

from broker import db
from broker.models import Operation, ServiceInstance


class BaseFactory(SQLAlchemyModelFactory):
    class Meta(object):
        sqlalchemy_session = db.session  # the SQLAlchemy session object
        sqlalchemy_session_persistence = "flush"


class ServiceInstanceFactory(BaseFactory):
    class Meta(object):
        model = ServiceInstance

    id = Sequence(lambda n: "UUID {}".format(n))


class OperationFactory(BaseFactory):
    class Meta(object):
        model = Operation

    state = OperationState.IN_PROGRESS
    service_instance = SubFactory(ServiceInstanceFactory)
