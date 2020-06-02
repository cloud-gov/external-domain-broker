import logging

from broker.tasks import cloudfront, finalize, iam, letsencrypt, route53
from broker.tasks.huey import huey

logger = logging.getLogger(__name__)


def queue_all_provision_tasks_for_operation(operation_id: int, correlation_id: str):
    if correlation_id is None:
        raise RuntimeError("correlation_id must be set")
    if operation_id is None:
        raise RuntimeError("operation_id must be set")
    task_pipeline = (
        letsencrypt.create_user.s(operation_id, correlation_id=correlation_id)
        .then(
            letsencrypt.generate_private_key,
            operation_id,
            correlation_id=correlation_id,
        )
        .then(
            letsencrypt.initiate_challenges, operation_id, correlation_id=correlation_id
        )
        .then(route53.create_TXT_records, operation_id, correlation_id=correlation_id)
        .then(route53.wait_for_changes, operation_id, correlation_id=correlation_id)
        .then(
            letsencrypt.answer_challenges, operation_id, correlation_id=correlation_id
        )
        .then(
            letsencrypt.retrieve_certificate,
            operation_id,
            correlation_id=correlation_id,
        )
        .then(
            iam.upload_server_certificate, operation_id, correlation_id=correlation_id
        )
        .then(
            cloudfront.create_distribution, operation_id, correlation_id=correlation_id
        )
        .then(
            cloudfront.wait_for_distribution,
            operation_id,
            correlation_id=correlation_id,
        )
        .then(route53.create_ALIAS_records, operation_id, correlation_id=correlation_id)
        .then(route53.wait_for_changes, operation_id, correlation_id=correlation_id)
        .then(finalize.provision, operation_id, correlation_id=correlation_id,)
    )
    huey.enqueue(task_pipeline)


def queue_all_deprovision_tasks_for_operation(operation_id: int, correlation_id: str):
    if correlation_id is None:
        raise RuntimeError("correlation_id must be set")
    if operation_id is None:
        raise RuntimeError("operation_id must be set")
    task_pipeline = (
        route53.remove_ALIAS_records.s(operation_id, correlation_id=correlation_id)
        .then(route53.remove_TXT_records, operation_id, correlation_id=correlation_id)
        .then(
            cloudfront.disable_distribution, operation_id, correlation_id=correlation_id
        )
        .then(
            cloudfront.wait_for_distribution_disabled,
            operation_id,
            correlation_id=correlation_id,
        )
        .then(
            cloudfront.delete_distribution, operation_id, correlation_id=correlation_id,
        )
        .then(
            iam.delete_server_certificate, operation_id, correlation_id=correlation_id
        )
        .then(finalize.deprovision, operation_id, correlation_id=correlation_id,)
    )
    huey.enqueue(task_pipeline)
