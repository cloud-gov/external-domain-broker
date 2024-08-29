from broker.tasks import (
    update_operations,
    iam,
    letsencrypt,
    route53,
    cloudfront,
)
from broker.tasks.huey import huey


def queue_all_cdn_provision_tasks_for_operation(operation_id: int, correlation_id: str):
    if correlation_id is None:
        raise RuntimeError("correlation_id must be set")
    if operation_id is None:
        raise RuntimeError("operation_id must be set")
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        letsencrypt.create_user.s(operation_id, **correlation)
        .then(letsencrypt.generate_private_key, operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_server_certificate, operation_id, **correlation)
        .then(cloudfront.create_distribution, operation_id, **correlation)
        .then(cloudfront.wait_for_distribution, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(update_operations.provision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_cdn_deprovision_tasks_for_operation(
    operation_id: int, correlation_id: str
):
    if correlation_id is None:
        raise RuntimeError("correlation_id must be set")
    if operation_id is None:
        raise RuntimeError("operation_id must be set")
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        update_operations.cancel_pending_provisioning.s(operation_id, **correlation)
        .then(route53.remove_ALIAS_records, operation_id, **correlation)
        .then(route53.remove_TXT_records, operation_id, **correlation)
        .then(cloudfront.disable_distribution, operation_id, **correlation)
        .then(cloudfront.wait_for_distribution_disabled, operation_id, **correlation)
        .then(cloudfront.delete_distribution, operation_id=operation_id, **correlation)
        .then(iam.delete_server_certificate, operation_id, **correlation)
        .then(update_operations.deprovision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_cdn_update_tasks_for_operation(operation_id, correlation_id):
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        letsencrypt.generate_private_key.s(operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_server_certificate, operation_id, **correlation)
        .then(cloudfront.update_distribution, operation_id, **correlation)
        .then(cloudfront.wait_for_distribution, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(iam.delete_previous_server_certificate, operation_id, **correlation)
        .then(update_operations.update_complete, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_cdn_renewal_tasks_for_operation(operation_id, **kwargs):
    correlation = {"correlation_id": "Renewal"}
    task_pipeline = (
        letsencrypt.generate_private_key.s(operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_server_certificate, operation_id, **correlation)
        .then(cloudfront.update_certificate, operation_id, **correlation)
        .then(iam.delete_previous_server_certificate, operation_id, **correlation)
        .then(update_operations.provision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)
