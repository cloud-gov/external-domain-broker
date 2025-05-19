import pytest  # noqa F401

from broker.extensions import db
from broker.models import (
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
    Operation,
    ServiceInstance,
    ServiceInstanceTypes,
)

from tests.lib.client import check_last_operation_description

from tests.lib.cdn.update import (
    subtest_update_waits_for_cloudfront_update,
    subtest_update_updates_ALIAS_records,
    subtest_update_same_domains_does_not_create_new_certificate,
    subtest_update_same_domains_does_not_retrieve_new_certificate,
    subtest_update_same_domains_does_not_update_iam,
    subtest_update_same_domains_updates_cloudfront,
    subtest_update_same_domains_does_not_delete_server_certificate,
    subtest_update_same_domains_does_not_create_new_challenges,
    subtest_update_does_not_create_new_TXT_records,
    subtest_update_creates_private_key_and_csr,
    subtest_gets_new_challenges,
    subtest_update_creates_new_TXT_records,
    subtest_waits_for_dns_changes,
    subtest_update_answers_challenges,
    subtest_update_retrieves_new_cert,
    subtest_update_uploads_new_cert,
    subtest_updates_cloudfront,
    subtest_update_waits_for_cloudfront_update,
    subtest_update_updates_ALIAS_records,
    subtest_waits_for_dns_changes,
    subtest_update_removes_certificate_from_iam,
    subtest_update_marks_update_complete,
)
from tests.lib.update import (
    subtest_waits_for_dns_changes,
    subtest_update_marks_update_complete,
)
from tests.integration.cdn.test_cdn_provisioning import subtest_provision_cdn_instance
from tests.integration.cdn_dedicated_waf.provision import (
    subtest_provision_create_web_acl,
    subtest_provision_creates_health_checks,
    subtest_provision_associate_health_check,
    subtest_provision_creates_health_check_alarms,
    subtest_provision_creates_sns_notification_topic,
    subtest_provision_creates_ddos_detected_alarm,
    subtest_provision_subscribes_sns_notification_topic,
)


def test_update_plan_only(
    client,
    tasks,
    route53,
    cloudfront,
    wafv2,
    shield,
    dns,
    iam_commercial,
    cloudwatch_commercial,
    sns_commercial,
    simple_regex,
    organization_guid,
    space_guid,
):
    # Create initial cdn_service_instance plan instance
    subtest_provision_cdn_instance(
        client,
        dns,
        tasks,
        route53,
        iam_commercial,
        simple_regex,
        cloudfront,
        organization_guid,
        space_guid,
    )

    subtest_is_cdn_instance()

    # Test upgrade from cdn_service_instance plan to cdn_dedicated_waf_service_instance plan
    operation_id = subtest_creates_update_plan_operation(client, "4321")
    subtest_is_cdn_dedicated_waf_instance()
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    instance_model = CDNDedicatedWAFServiceInstance
    subtest_update_same_domains_does_not_create_new_certificate(
        tasks,
        instance_model,
    )
    subtest_update_same_domains_does_not_create_new_challenges(tasks, instance_model)
    subtest_update_does_not_create_new_TXT_records(tasks, route53, instance_model)
    subtest_update_same_domains_does_not_retrieve_new_certificate(tasks)
    subtest_update_same_domains_does_not_update_iam(tasks)
    subtest_provision_create_web_acl(tasks, wafv2, instance_model)
    subtest_update_same_domains_updates_cloudfront(
        tasks,
        cloudfront,
        instance_model,
        expect_update_domain_names=["example.com", "foo.com"],
        expect_forward_cookie_policy=CDNServiceInstance.ForwardCookiePolicy.WHITELIST.value,
        expect_forwarded_cookies=["mycookie", "myothercookie"],
        expect_origin_hostname="origin.com",
        expect_origin_path="/somewhere",
        expect_origin_protocol_policy="http-only",
        expect_custom_error_responses={
            "Quantity": 2,
            "Items": [
                {
                    "ErrorCode": 404,
                    "ResponsePagePath": "/errors/404.html",
                    "ResponseCode": "404",
                    "ErrorCachingMinTTL": 300,
                },
                {
                    "ErrorCode": 405,
                    "ResponsePagePath": "/errors/405.html",
                    "ResponseCode": "405",
                    "ErrorCachingMinTTL": 300,
                },
            ],
        },
    )
    subtest_update_waits_for_cloudfront_update(tasks, cloudfront, instance_model)
    subtest_update_updates_ALIAS_records(
        tasks,
        route53,
        instance_model,
        expected_domains=["example.com", "foo.com"],
    )
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_same_domains_does_not_delete_server_certificate(
        tasks, instance_model
    )
    subtest_provision_creates_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    subtest_provision_subscribes_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    subtest_provision_creates_health_checks(tasks, route53, instance_model)
    subtest_provision_associate_health_check(tasks, shield, instance_model)
    subtest_provision_creates_health_check_alarms(
        tasks, cloudwatch_commercial, instance_model
    )
    subtest_provision_creates_ddos_detected_alarm(
        tasks, cloudwatch_commercial, instance_model
    )
    subtest_update_marks_update_complete(tasks, instance_model)


def test_update_plan_and_domains(
    client,
    tasks,
    route53,
    cloudfront,
    wafv2,
    shield,
    dns,
    iam_commercial,
    cloudwatch_commercial,
    sns_commercial,
    simple_regex,
    organization_guid,
    space_guid,
):
    # Create initial cdn_service_instance plan instance
    subtest_provision_cdn_instance(
        client,
        dns,
        tasks,
        route53,
        iam_commercial,
        simple_regex,
        cloudfront,
        organization_guid,
        space_guid,
    )

    subtest_is_cdn_instance()

    # Test upgrade from cdn_service_instance plan to cdn_dedicated_waf_service_instance plan
    # with update to domains for instance
    instance_model = CDNDedicatedWAFServiceInstance
    operation_id = subtest_update_creates_update_plan_and_domains_operation(
        client, dns, instance_model
    )
    subtest_is_cdn_dedicated_waf_instance()
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_update_creates_private_key_and_csr(tasks, instance_model)
    subtest_gets_new_challenges(tasks, instance_model)
    subtest_update_creates_new_TXT_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_answers_challenges(tasks, dns, instance_model)
    subtest_update_retrieves_new_cert(tasks, instance_model)
    subtest_update_uploads_new_cert(tasks, iam_commercial, simple_regex, instance_model)
    subtest_provision_create_web_acl(tasks, wafv2, instance_model)
    subtest_updates_cloudfront(tasks, cloudfront, instance_model)
    subtest_update_waits_for_cloudfront_update(tasks, cloudfront, instance_model)
    subtest_update_updates_ALIAS_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_removes_certificate_from_iam(tasks, iam_commercial, instance_model)
    subtest_provision_creates_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    subtest_provision_subscribes_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    subtest_provision_creates_health_checks(
        tasks, route53, instance_model, expected_domain_names=["bar.com", "foo.com"]
    )
    check_last_operation_description(
        client, "4321", operation_id, "Creating new health checks"
    )
    subtest_provision_associate_health_check(
        tasks, shield, instance_model, expected_domain_name="bar.com"
    )
    check_last_operation_description(
        client, "4321", operation_id, "Associating health check with Shield"
    )
    subtest_provision_creates_health_check_alarms(
        tasks, cloudwatch_commercial, instance_model
    )
    subtest_provision_creates_ddos_detected_alarm(
        tasks, cloudwatch_commercial, instance_model
    )
    subtest_update_marks_update_complete(tasks, instance_model)


def subtest_creates_update_plan_operation(client, service_instance_id):
    client.update_cdn_to_cdn_dedicated_waf_instance(
        service_instance_id, params={"alarm_notification_email": "fake@local.host"}
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == service_instance_id

    service_instance = db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.alarm_notification_email == "fake@local.host"

    return operation_id


def subtest_update_creates_update_plan_and_domains_operation(
    client, dns, instance_model, service_instance_id="4321"
):
    dns.add_cname("_acme-challenge.foo.com")
    dns.add_cname("_acme-challenge.bar.com")
    client.update_cdn_to_cdn_dedicated_waf_instance(
        service_instance_id,
        params={
            "domains": "bar.com, Foo.com",
            "origin": "new-origin.com",
            "path": "/somewhere-else",
            "forward_cookies": "mycookie,myothercookie, anewcookie",
            "forward_headers": "x-my-header, x-your-header   ",
            "insecure_origin": True,
            "alarm_notification_email": "fake@local.host",
        },
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == service_instance_id

    instance = db.session.get(instance_model, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "new-origin.com"
    assert instance.cloudfront_origin_path == "/somewhere-else"
    assert instance.alarm_notification_email == "fake@local.host"

    return operation_id


def subtest_is_cdn_instance(service_instance_id="4321"):
    db.session.expunge_all()
    instance = db.session.get(ServiceInstance, service_instance_id)
    assert instance.instance_type == ServiceInstanceTypes.CDN.value


def subtest_is_cdn_dedicated_waf_instance(service_instance_id="4321"):
    db.session.expunge_all()
    instance = db.session.get(ServiceInstance, service_instance_id)
    assert instance.instance_type == ServiceInstanceTypes.CDN_DEDICATED_WAF.value
