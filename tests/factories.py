from broker import db
from factory import Sequence
from factory.alchemy import SQLAlchemyModelFactory
from broker.models import ServiceInstance


class ServiceInstanceFactory(SQLAlchemyModelFactory):
    class Meta(object):
        model = ServiceInstance
        sqlalchemy_session = db.session  # the SQLAlchemy session object

    id = Sequence(lambda n: "UUID {}".format(n))
