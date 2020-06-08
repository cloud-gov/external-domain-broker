import logging
from datetime import datetime

from broker.models import Operation
from broker.tasks import huey
from broker.tasks.db_injection import inject_db

logger = logging.getLogger(__name__)


@huey.retriable_task
@inject_db
def provision(operation_id: str, **kwargs):
    db = kwargs['db']
    operation = Operation.query.get(operation_id)
    operation.state = Operation.States.SUCCEEDED.value
    db.session.add(operation)
    db.session.commit()


@huey.retriable_task
@inject_db
def deprovision(operation_id: str, **kwargs):
    db = kwargs['db']
    operation = Operation.query.get(operation_id)
    operation.state = Operation.States.SUCCEEDED.value
    db.session.add(operation)

    service_instance = operation.service_instance
    service_instance.deactivated_at = datetime.utcnow()
    service_instance.private_key_pem = None
    db.session.add(service_instance)

    db.session.commit()
