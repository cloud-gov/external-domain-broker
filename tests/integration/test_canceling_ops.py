import json
from datetime import date, datetime

import pytest  # noqa F401

from huey.exceptions import CancelExecution

from broker.extensions import config, db
from broker.models import Challenge, Operation, CDNServiceInstance
from tests.lib.factories import (
    OperationFactory,
    CDNServiceInstanceFactory,
    ALBServiceInstanceFactory,
)

from broker.tasks.huey import huey

from broker.tasks.alb import select_alb, add_certificate_to_alb
from broker.tasks.cloudfront import create_distribution, wait_for_distribution
from broker.tasks.iam import upload_server_certificate
from broker.tasks.route53 import create_ALIAS_records, create_TXT_records
from broker.tasks.letsencrypt import (
    create_user,
    answer_challenges,
    initiate_challenges,
    retrieve_certificate,
    generate_private_key,
)


params = [
    select_alb,
    add_certificate_to_alb,
    create_distribution,
    wait_for_distribution,
    upload_server_certificate,
    create_ALIAS_records,
    create_TXT_records,
    create_user,
    answer_challenges,
    initiate_challenges,
    retrieve_certificate,
    generate_private_key,
]


@pytest.mark.parametrize("task_type", params)
def test_noop_when_operation_canceled(clean_db, task_type):
    op = OperationFactory.create(id="4321", canceled_at=datetime.now())
    db.session.refresh(op)
    task = task_type.s("4321")
    with pytest.raises(CancelExecution):
        for name, callback in huey._pre_execute.items():
            callback(task)


@pytest.mark.parametrize("task_type", params)
def test_no_cancel_for_uncanceled_tasks(clean_db, task_type):
    op = OperationFactory.create(id="4321")
    db.session.refresh(op)
    task = task_type.s("4321")
    for name, callback in huey._pre_execute.items():
        callback(task)


def test_cancel_operation_cdn(client, tasks):
    service_instance = CDNServiceInstanceFactory.create(id="4321")
    in_progress = OperationFactory.create(
        service_instance=service_instance,
        state=Operation.States.IN_PROGRESS.value,
        action=Operation.Actions.PROVISION.value,
    )
    completed = OperationFactory.create(
        service_instance=service_instance,
        state=Operation.States.SUCCEEDED.value,
        action=Operation.Actions.PROVISION.value,
    )
    failed = OperationFactory.create(
        service_instance=service_instance,
        state=Operation.States.FAILED.value,
        action=Operation.Actions.PROVISION.value,
    )
    in_progress_id = in_progress.id
    completed_id = completed.id
    failed_id = failed.id

    client.deprovision_cdn_instance("4321")
    tasks.run_queued_tasks_and_enqueue_dependents()

    # reinstantiate these because we are really messing with sqlalchemy's idea of what a session should look like
    in_progress = db.session.get(Operation, in_progress_id)
    failed = db.session.get(Operation, failed_id)
    completed = db.session.get(Operation, completed_id)

    assert in_progress.canceled_at is not None
    assert completed.canceled_at is None
    assert failed.canceled_at is None


def test_cancel_operation_alb(client, tasks):
    service_instance = ALBServiceInstanceFactory.create(id="4321")
    in_progress = OperationFactory.create(
        service_instance=service_instance,
        state=Operation.States.IN_PROGRESS.value,
        action=Operation.Actions.PROVISION.value,
    )
    completed = OperationFactory.create(
        service_instance=service_instance,
        state=Operation.States.SUCCEEDED.value,
        action=Operation.Actions.PROVISION.value,
    )
    failed = OperationFactory.create(
        service_instance=service_instance,
        state=Operation.States.FAILED.value,
        action=Operation.Actions.PROVISION.value,
    )
    in_progress_id = in_progress.id
    completed_id = completed.id
    failed_id = failed.id

    client.deprovision_alb_instance("4321")
    tasks.run_queued_tasks_and_enqueue_dependents()

    # reinstantiate these because we are really messing with sqlalchemy's idea of what a session should look like
    in_progress = db.session.get(Operation, in_progress_id)
    failed = db.session.get(Operation, failed_id)
    completed = db.session.get(Operation, completed_id)

    assert in_progress.canceled_at is not None
    assert completed.canceled_at is None
    assert failed.canceled_at is None
