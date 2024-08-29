import logging

from broker.tasks import (
    alb,
    cloudfront,
    update_operations,
    iam,
    letsencrypt,
    route53,
)
from broker.tasks.huey import huey

logger = logging.getLogger(__name__)


def queue_all_migration_deprovision_tasks_for_operation(
    operation_id: int, correlation_id: str
):
    if correlation_id is None:
        raise RuntimeError("correlation_id must be set")
    if operation_id is None:
        raise RuntimeError("operation_id must be set")
    correlation = {"correlation_id": correlation_id}
    task_pipeline = update_operations.deprovision.s(operation_id, **correlation)
    huey.enqueue(task_pipeline)


def queue_all_cdn_broker_migration_tasks_for_operation(operation_id, correlation_id):
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        cloudfront.remove_s3_bucket_from_cdn_broker_instance.s(
            operation_id, **correlation
        )
        .then(cloudfront.add_logging_to_bucket, operation_id, **correlation)
        .then(letsencrypt.create_user, operation_id, **correlation)
        .then(letsencrypt.generate_private_key, operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
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


def queue_all_domain_broker_migration_tasks_for_operation(operation_id, correlation_id):
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        letsencrypt.create_user.s(operation_id, **correlation)
        .then(letsencrypt.generate_private_key, operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        # create alias records here is probably not necessary, but belt + suspenders
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_server_certificate, operation_id, **correlation)
        .then(alb.select_alb, operation_id, **correlation)
        .then(alb.add_certificate_to_alb, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(alb.remove_certificate_from_previous_alb, operation_id, **correlation)
        .then(iam.delete_previous_server_certificate, operation_id, **correlation)
        .then(update_operations.provision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)
