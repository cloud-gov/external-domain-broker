import time
import pytest

from huey.exceptions import TaskException
from broker.extensions import config, db
from broker.tasks.huey import huey
from broker.tasks.letsencrypt import initiate_challenges
from broker.models import Operation

from tests.lib.factories import OperationFactory
from tests.lib.tasks import fallible_huey, immediate_huey


def test_operations_marked_failed_after_failing(
    tasks, no_context_clean_db, no_context_app
):
    @huey.task()
    def no_retry_task(operation_id):
        raise Exception()

    @huey.task()
    def semaphore_task(operation_id):
        # this task deletes our operation
        # so tests will fail if the task failure logic
        # doesn't abort the rest of the pipeline

        with no_context_app.app_context():
            operation = Operation.query.get(operation_id)
            db.session.delete(operation)
            db.session.commit()

    with no_context_app.app_context():
        no_retries_left_operation = OperationFactory.create(
            id="9876",
            state="InProgress",
            action="Provision",
            service_instance_id="nonextistent",
        )
        db.session.commit()
    with fallible_huey() as h:
        with immediate_huey() as h:
            # this task should fail because we have not created a user
            pipeline = no_retry_task.s("9876").then(semaphore_task, "9876")
            h.enqueue(pipeline)
    with no_context_app.app_context():
        no_retries_left_operation = Operation.query.get("9876")
    assert no_retries_left_operation.state == "failed"


def test_retry_tasks_marked_failed_only_after_last_retry():
    global retry_marked_failed
    retry_marked_failed = False

    @huey.task(retries=7)
    def retry_task(operation_id):
        operation = Operation.query.get(operation_id)
        global retry_marked_failed
        if operation.state == "failed":
            retry_marked_failed = True
        raise Exception()

    operation_with_retries = OperationFactory.create(
        id="6789",
        state="InProgress",
        action="Provision",
        service_instance_id="nonextistent",
    )
    db.session.commit()
    with fallible_huey() as h:
        with immediate_huey() as h:
            # this task should fail because we have not created a user
            task = retry_task("6789")
            with pytest.raises(TaskException):
                result = task()
    operation_with_retries = Operation.query.get("6789")
    assert operation_with_retries.state == "failed"
    assert not retry_marked_failed
