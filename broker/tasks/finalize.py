import logging
from datetime import datetime

from broker.extensions import db
from broker.models import Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.retriable_task
def provision(operation_id: str, **kwargs):
    operation = Operation.query.get(operation_id)
    operation.state = Operation.States.SUCCEEDED.value
    db.session.add(operation)
    db.session.commit()


@huey.retriable_task
def deprovision(operation_id: str, **kwargs):
    operation = Operation.query.get(operation_id)
    operation.state = Operation.States.SUCCEEDED.value
    db.session.add(operation)

    service_instance = operation.service_instance
    service_instance.deactivated_at = datetime.utcnow()
    service_instance.private_key_pem = None
    db.session.add(service_instance)

    db.session.commit()
