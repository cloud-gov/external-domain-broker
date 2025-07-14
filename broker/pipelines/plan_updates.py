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
    sns,
    update_instances,
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
        .then(waf.create_alb_web_acl, operation_id, **correlation)
        .then(waf.put_alb_waf_logging_configuration, operation_id, **correlation)
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


def queue_all_dedicated_alb_to_cdn_dedicated_waf_update_tasks_for_operation(
    operation_id, correlation_id
):
    if correlation_id is None:
        raise RuntimeError("correlation_id must be set")
    if operation_id is None:
        raise RuntimeError("operation_id must be set")
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        alb.store_alb_certificate.s(operation_id, **correlation)
        .then(letsencrypt.generate_private_key, operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(route53.remove_old_DNS_records, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_cloudfront_server_certificate, operation_id, **correlation)
        .then(waf.create_cdn_web_acl, operation_id, **correlation)
        .then(waf.put_cdn_waf_logging_configuration, operation_id, **correlation)
        .then(cloudfront.create_distribution, operation_id, **correlation)
        .then(cloudfront.wait_for_distribution, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(sns.create_notification_topic, operation_id, **correlation)
        .then(sns.subscribe_notification_topic, operation_id, **correlation)
        .then(route53.create_new_health_checks, operation_id, **correlation)
        .then(shield.associate_health_check, operation_id, **correlation)
        .then(cloudwatch.create_health_check_alarms, operation_id, **correlation)
        .then(cloudwatch.create_ddos_detected_alarm, operation_id, **correlation)
        .then(
            alb.remove_alb_certificate_during_update_to_cdn_dedicated_waf,
            operation_id,
            **correlation,
        )
        .then(iam.delete_previous_alb_server_certificate, operation_id, **correlation)
        .then(
            update_instances.change_to_cdn_dedicated_waf_instance_type,
            operation_id,
            **correlation,
        )
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
        .then(waf.create_cdn_web_acl, operation_id, **correlation)
        .then(cloudfront.update_distribution, operation_id, **correlation)
        .then(cloudfront.wait_for_distribution, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(iam.delete_previous_server_certificate, operation_id, **correlation)
        .then(sns.create_notification_topic, operation_id, **correlation)
        .then(sns.subscribe_notification_topic, operation_id, **correlation)
        .then(route53.create_new_health_checks, operation_id, **correlation)
        .then(shield.associate_health_check, operation_id, **correlation)
        .then(cloudwatch.create_health_check_alarms, operation_id, **correlation)
        .then(cloudwatch.create_ddos_detected_alarm, operation_id, **correlation)
        .then(update_operations.update_complete, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)
