from broker.tasks import (
    alb,
    cloudfront,
    update_operations,
    iam,
    letsencrypt,
    route53,
    waf,
    shield,
    cloudwatch,
)
from broker.tasks.huey import huey


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
        .then(cloudwatch.create_health_check_alarms, operation_id, **correlation)
        .then(update_operations.update_complete, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)
