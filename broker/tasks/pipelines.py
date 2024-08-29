import logging

from broker.tasks import (
    alb,
    cloudfront,
    update_operations,
    iam,
    letsencrypt,
    route53,
    waf,
    shield,
)
from broker.tasks.huey import huey

logger = logging.getLogger(__name__)


def queue_all_dedicated_alb_provision_tasks_for_operation(
    operation_id: int, correlation_id: str
):
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
        .then(alb.select_dedicated_alb, operation_id, **correlation)
        .then(alb.add_certificate_to_alb, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(update_operations.provision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_alb_provision_tasks_for_operation(operation_id: int, correlation_id: str):
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
        .then(alb.select_alb, operation_id, **correlation)
        .then(alb.add_certificate_to_alb, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(update_operations.provision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_alb_deprovision_tasks_for_operation(
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
        .then(alb.remove_certificate_from_alb, operation_id, **correlation)
        .then(iam.delete_server_certificate, operation_id, **correlation)
        .then(update_operations.deprovision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


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


def queue_all_cdn_dedicated_waf_provision_tasks_for_operation(
    operation_id: int, correlation_id: str
):
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
        .then(waf.create_web_acl, operation_id, **correlation)
        .then(cloudfront.create_distribution, operation_id, **correlation)
        .then(cloudfront.wait_for_distribution, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(route53.create_health_checks, operation_id, **correlation)
        .then(shield.associate_health_check, operation_id, **correlation)
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


def queue_all_cdn_dedicated_waf_deprovision_tasks_for_operation(
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
        .then(shield.disassociate_health_check, operation_id, **correlation)
        .then(route53.delete_health_checks, operation_id, **correlation)
        .then(cloudfront.disable_distribution, operation_id, **correlation)
        .then(cloudfront.wait_for_distribution_disabled, operation_id, **correlation)
        .then(cloudfront.delete_distribution, operation_id=operation_id, **correlation)
        .then(waf.delete_web_acl, operation_id=operation_id, **correlation)
        .then(iam.delete_server_certificate, operation_id, **correlation)
        .then(update_operations.deprovision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_dedicated_alb_renewal_tasks_for_operation(operation_id, **kwargs):
    correlation = {"correlation_id": "Renewal"}
    task_pipeline = (
        letsencrypt.generate_private_key.s(operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_server_certificate, operation_id, **correlation)
        .then(alb.select_dedicated_alb, operation_id, **correlation)
        .then(alb.add_certificate_to_alb, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(alb.remove_certificate_from_previous_alb, operation_id, **correlation)
        .then(iam.delete_previous_server_certificate, operation_id, **correlation)
        .then(update_operations.provision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_alb_to_dedicated_alb_update_tasks_for_operation(
    operation_id, correlation_id
):
    if correlation_id is None:
        raise RuntimeError("correlation_id must be set")
    if operation_id is None:
        raise RuntimeError("operation_id must be set")
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        alb.select_dedicated_alb.s(operation_id, **correlation)
        .then(alb.add_certificate_to_alb, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(
            alb.remove_certificate_from_previous_alb_during_update_to_dedicated,
            operation_id,
            **correlation,
        )
        .then(update_operations.provision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_alb_renewal_tasks_for_operation(operation_id, **kwargs):
    correlation = {"correlation_id": "Renewal"}
    task_pipeline = (
        letsencrypt.generate_private_key.s(operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
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


def queue_all_cdn_dedicated_waf_update_tasks_for_operation(
    operation_id, correlation_id
):
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        letsencrypt.generate_private_key.s(operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_server_certificate, operation_id, **correlation)
        .then(waf.create_web_acl, operation_id, **correlation)
        .then(cloudfront.update_distribution, operation_id, **correlation)
        .then(cloudfront.wait_for_distribution, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(iam.delete_previous_server_certificate, operation_id, **correlation)
        .then(route53.create_new_health_checks, operation_id, **correlation)
        .then(shield.update_associated_health_check, operation_id, **correlation)
        .then(route53.delete_unused_health_checks, operation_id, **correlation)
        .then(update_operations.update_complete, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_cdn_to_cdn_dedicated_waf_update_tasks_for_operation(
    operation_id, correlation_id
):
    if correlation_id is None:
        raise RuntimeError("correlation_id must be set")
    if operation_id is None:
        raise RuntimeError("operation_id must be set")
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        letsencrypt.generate_private_key.s(operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_server_certificate, operation_id, **correlation)
        .then(waf.create_web_acl, operation_id, **correlation)
        .then(cloudfront.update_distribution, operation_id, **correlation)
        .then(cloudfront.wait_for_distribution, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(iam.delete_previous_server_certificate, operation_id, **correlation)
        .then(route53.create_health_checks, operation_id, **correlation)
        .then(shield.associate_health_check, operation_id, **correlation)
        .then(update_operations.update_complete, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_dedicated_alb_update_tasks_for_operation(operation_id, correlation_id):
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        letsencrypt.generate_private_key.s(operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_server_certificate, operation_id, **correlation)
        .then(alb.select_dedicated_alb, operation_id, **correlation)
        .then(alb.add_certificate_to_alb, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(alb.remove_certificate_from_previous_alb, operation_id, **correlation)
        .then(iam.delete_previous_server_certificate, operation_id, **correlation)
        .then(update_operations.provision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)


def queue_all_alb_update_tasks_for_operation(operation_id, correlation_id):
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        letsencrypt.generate_private_key.s(operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
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
