import logging
from datetime import datetime

from huey.exceptions import CancelExecution

from broker.extensions import db
from broker.models import Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.huey.pre_execute(name="Cancel tasks for canceled operations")
def cancel_canceled_operations(task):
    with huey.huey.flask_app.app_context():
        args, kwargs = task.data
        op = None
        try:
            # big assumption here: the first arg will always be the operation id.
            op = Operation.query.get(args[0])
        except:
            return
        finally:
            db.session.close()
        if op.canceled_at is not None:
            raise CancelExecution


@huey.retriable_task
def provision(operation_id: str, **kwargs):
    operation = Operation.query.get(operation_id)
    operation.state = Operation.States.SUCCEEDED.value
    operation.step_description = "Complete!"
    db.session.add(operation)
    db.session.commit()


@huey.retriable_task
def deprovision(operation_id: str, **kwargs):
    operation = Operation.query.get(operation_id)
    operation.state = Operation.States.SUCCEEDED.value
    operation.step_description = "Complete!"
    db.session.add(operation)

    service_instance = operation.service_instance
    service_instance.deactivated_at = datetime.utcnow()
    service_instance.private_key_pem = None
    db.session.add(service_instance)

    db.session.commit()


@huey.retriable_task
def cancel_pending_provisioning(operation_id: str, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    for op in service_instance.operations:
        if (
            op.action == Operation.Actions.PROVISION.value
            and op.state == Operation.States.IN_PROGRESS.value
        ):
            op.canceled_at = datetime.utcnow()
            db.session.add(op)
    db.session.commit()
