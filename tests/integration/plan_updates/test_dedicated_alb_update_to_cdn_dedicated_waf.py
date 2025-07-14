from broker.lib.cdn import is_cdn_dedicated_waf_instance
from broker.extensions import db
from broker.models import (
    CDNDedicatedWAFServiceInstance,
    MigrateDedicatedALBToCDNDedicatedWafServiceInstance,
    Operation,
    ServiceInstanceTypes,
)

from tests.lib.client import check_last_operation_description

from tests.lib.provision import (
    subtest_provision_initiates_LE_challenge,
    subtest_provision_answers_challenges,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
)
from tests.lib.update import (
    subtest_update_creates_private_key_and_csr,
    subtest_update_retrieves_new_cert,
    subtest_update_removes_certificate_from_iam,
    subtest_update_marks_update_complete,
)
from tests.lib.cdn.update import (
    subtest_update_does_not_remove_old_TXT_records,
)

from tests.lib.cdn.provision import (
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_waits_for_cloudfront_distribution,
    subtest_provision_provisions_ALIAS_records,
    subtest_provision_waits_for_route53_changes,
)
from tests.integration.cdn_dedicated_waf.provision import (
    subtest_provision_create_web_acl,
    subtest_provision_put_web_acl_logging_configuration,
    subtest_provision_creates_sns_notification_topic,
    subtest_provision_subscribes_sns_notification_topic,
    subtest_provision_creates_health_checks,
    subtest_provision_associate_health_check,
    subtest_provision_creates_health_check_alarms,
    subtest_provision_creates_ddos_detected_alarm,
)
from tests.integration.dedicated_alb.test_dedicated_alb_provisioning import (
    subtest_provision_dedicated_alb_instance,
)


def test_update_dedicated_alb_to_cdn_dedicated_waf_happy_path(
    client,
    dns,
    tasks,
    route53,
    iam_govcloud,
    simple_regex,
    alb,
    organization_guid,
    space_guid,
    clean_db,
    service_instance_id,
    iam_commercial,
    wafv2_commercial,
    cloudfront,
    sns_commercial,
    cloudwatch_commercial,
    shield,
    wafv2_govcloud,
    dedicated_alb_id,
):
    subtest_provision_dedicated_alb_instance(
        client,
        dns,
        tasks,
        route53,
        iam_govcloud,
        simple_regex,
        alb,
        organization_guid,
        space_guid,
        wafv2_govcloud,
        dedicated_alb_id,
        service_instance_id=service_instance_id,
    )

    operation_id = subtest_migrate_creates_update_plan_operation(
        client, clean_db, service_instance_id
    )

    check_last_operation_description(
        client, service_instance_id, operation_id, "Queuing tasks"
    )

    instance_model = MigrateDedicatedALBToCDNDedicatedWafServiceInstance

    subtest_migrate_store_alb_certificate(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Storing ALB certificate information"
    )
    subtest_update_creates_private_key_and_csr(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Creating credentials for Lets Encrypt",
    )
    subtest_provision_initiates_LE_challenge(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Initiating Lets Encrypt challenges"
    )
    subtest_provision_updates_TXT_records(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Updating DNS TXT records"
    )
    subtest_provision_waits_for_route53_changes(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Waiting for DNS changes"
    )
    subtest_update_does_not_remove_old_TXT_records(tasks, route53)
    check_last_operation_description(
        client, service_instance_id, operation_id, "Removing old DNS records"
    )
    subtest_provision_answers_challenges(
        tasks, dns, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Answering Lets Encrypt challenges"
    )
    subtest_update_retrieves_new_cert(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Retrieving SSL certificate from Lets Encrypt",
    )
    subtest_provision_uploads_certificate_to_iam(
        tasks,
        iam_commercial,
        simple_regex,
        instance_model,
        service_instance_id=service_instance_id,
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Uploading SSL certificate to AWS",
    )
    subtest_provision_create_web_acl(
        tasks, wafv2_commercial, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Creating custom WAFv2 web ACL",
    )
    subtest_provision_put_web_acl_logging_configuration(
        tasks, wafv2_commercial, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Updating WAFv2 web ACL logging configuration",
    )
    subtest_migrate_creates_cloudfront_distribution(
        tasks, cloudfront, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Creating CloudFront distribution",
    )
    subtest_provision_waits_for_cloudfront_distribution(
        tasks, cloudfront, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Waiting for CloudFront distribution",
    )
    subtest_provision_provisions_ALIAS_records(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Creating DNS ALIAS records",
    )
    subtest_provision_waits_for_route53_changes(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Waiting for DNS changes",
    )
    subtest_provision_creates_sns_notification_topic(
        tasks, sns_commercial, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Creating SNS notification topic"
    )
    subtest_provision_subscribes_sns_notification_topic(
        tasks, sns_commercial, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Subscribing to SNS notification topic",
    )
    subtest_provision_creates_health_checks(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Creating new health checks"
    )
    subtest_provision_associate_health_check(
        tasks, shield, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Associating health check with Shield",
    )
    subtest_provision_creates_health_check_alarms(
        tasks,
        cloudwatch_commercial,
        instance_model,
        service_instance_id=service_instance_id,
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Creating Cloudwatch alarms for Route53 health checks",
    )
    subtest_provision_creates_ddos_detected_alarm(
        tasks,
        cloudwatch_commercial,
        instance_model,
        service_instance_id=service_instance_id,
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Creating DDoS detection alarm"
    )
    subtest_migrate_removes_certificate_from_alb(
        tasks, alb, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Removing SSL certificate from previous load balancer",
    )
    subtest_update_removes_certificate_from_iam(
        tasks, iam_govcloud, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Removing SSL certificate from AWS",
    )
    subtest_migrate_updates_to_cdn_dedicated_waf_instance(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Changing instance type to CDNDedicatedWAFServiceInstance",
    )
    instance_model = CDNDedicatedWAFServiceInstance
    subtest_update_marks_update_complete(
        tasks,
        instance_model,
        service_instance_id=service_instance_id,
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Complete!"
    )


def subtest_migrate_creates_update_plan_operation(
    client, clean_db, service_instance_id
):
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance_id, params={"alarm_notification_email": "fake@local.host"}
    )
    assert client.response.status_code == 202, client.response.json
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]

    operation = clean_db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == service_instance_id

    service_instance = db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance_id
    )
    assert service_instance.alarm_notification_email == "fake@local.host"

    return operation_id


def subtest_migrate_updates_to_cdn_dedicated_waf_instance(
    tasks, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert (
        service_instance.instance_type
        == ServiceInstanceTypes.DEDICATED_ALB_CDN_DEDICATED_WAF_MIGRATION.value
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )

    assert is_cdn_dedicated_waf_instance(service_instance) == True


def subtest_migrate_store_alb_certificate(
    tasks, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    current_certificate = service_instance.current_certificate

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    service_instance.alb_certificate = current_certificate


def subtest_migrate_removes_certificate_from_alb(
    tasks, alb, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    alb.expect_remove_certificate_from_listener(
        service_instance.alb_listener_arn,
        service_instance.alb_certificate.iam_server_certificate_arn,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.alb_certificate == None
    assert service_instance.previous_alb_arn == None
    assert service_instance.previous_alb_listener_arn == None

    alb.assert_no_pending_responses()


def subtest_migrate_creates_cloudfront_distribution(
    tasks, cloudfront, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    certificate = service_instance.new_certificate

    id_ = certificate.id

    dedicated_waf_web_acl_arn = service_instance.dedicated_waf_web_acl_arn

    cloudfront.expect_create_distribution_with_tags(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
        bucket_prefix=f"{service_instance_id}/",
        dedicated_waf_web_acl_arn=dedicated_waf_web_acl_arn,
        tags=service_instance.tags,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.cloudfront_distribution_arn
    assert service_instance.cloudfront_distribution_arn.startswith("arn:aws:cloudfront")
    assert service_instance.cloudfront_distribution_arn.endswith("FakeDistributionId")
    assert service_instance.cloudfront_distribution_id == "FakeDistributionId"
    assert service_instance.domain_internal == "fake1234.cloudfront.net"
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate is not None
    assert service_instance.current_certificate.id == id_
    assert service_instance.tags is not None
