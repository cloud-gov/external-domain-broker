from broker.tasks import (
    alb,
    update_operations,
    iam,
    letsencrypt,
    route53,
    waf,
)
from broker.tasks.huey import huey


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
        .then(waf.create_alb_web_acl, operation_id, **correlation)
        .then(waf.put_alb_waf_logging_configuration, operation_id, **correlation)
        .then(waf.associate_alb_web_acl, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(update_operations.provision, operation_id, **correlation)
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


def queue_all_dedicated_alb_update_tasks_for_operation(operation_id, correlation_id):
    correlation = {"correlation_id": correlation_id}
    task_pipeline = (
        letsencrypt.generate_private_key.s(operation_id, **correlation)
        .then(letsencrypt.initiate_challenges, operation_id, **correlation)
        .then(route53.create_TXT_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(route53.remove_old_DNS_records, operation_id, **correlation)
        .then(letsencrypt.answer_challenges, operation_id, **correlation)
        .then(letsencrypt.retrieve_certificate, operation_id, **correlation)
        .then(iam.upload_server_certificate, operation_id, **correlation)
        .then(alb.select_dedicated_alb, operation_id, **correlation)
        .then(alb.add_certificate_to_alb, operation_id, **correlation)
        .then(waf.create_alb_web_acl, operation_id, **correlation)
        .then(waf.put_alb_waf_logging_configuration, operation_id, **correlation)
        .then(waf.associate_alb_web_acl, operation_id, **correlation)
        .then(route53.create_ALIAS_records, operation_id, **correlation)
        .then(route53.wait_for_changes, operation_id, **correlation)
        .then(alb.remove_certificate_from_previous_alb, operation_id, **correlation)
        .then(iam.delete_previous_server_certificate, operation_id, **correlation)
        .then(update_operations.provision, operation_id, **correlation)
    )
    huey.enqueue(task_pipeline)
