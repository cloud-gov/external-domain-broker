import uuid

from broker.extensions import config, db
from broker.models import (
    CDNDedicatedWAFServiceInstance,
)
from broker.tasks.cloudwatch import _get_alarm_name, generate_ddos_alarm_name


def subtest_provision_create_web_acl(tasks, wafv2, service_instance_id="4321"):
    db.session.expunge_all()
    service_instance = db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )

    wafv2.expect_create_web_acl(
        service_instance.id,
        config.WAF_RATE_LIMIT_RULE_GROUP_ARN,
        service_instance.tags,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.dedicated_waf_web_acl_id
    web_acl_name = f"{config.AWS_RESOURCE_PREFIX}-{service_instance.id}-dedicated-waf"
    assert service_instance.dedicated_waf_web_acl_id == f"{web_acl_name}-id"
    assert service_instance.dedicated_waf_web_acl_name
    assert service_instance.dedicated_waf_web_acl_name == web_acl_name
    assert service_instance.dedicated_waf_web_acl_arn
    assert (
        service_instance.dedicated_waf_web_acl_arn
        == f"arn:aws:wafv2::000000000000:global/webacl/{web_acl_name}"
    )


def subtest_provision_creates_health_checks(
    tasks,
    route53,
    instance_model,
    service_instance_id="4321",
    expected_domain_names=["example.com", "foo.com"],
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    for idx, domain_name in enumerate(service_instance.domain_names):
        route53.expect_create_health_check(service_instance.id, domain_name, idx)
        route53.expect_change_tags_for_resource(domain_name, service_instance.tags)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert sorted(
        service_instance.route53_health_checks,
        key=lambda check: check["domain_name"],
    ) == sorted(
        [
            {"domain_name": domain, "health_check_id": f"{domain} ID"}
            for domain in expected_domain_names
        ],
        key=lambda check: check["domain_name"],
    )
    route53.assert_no_pending_responses()


def subtest_provision_associate_health_check(
    tasks,
    shield,
    instance_model,
    service_instance_id="4321",
    expected_domain_name="example.com",
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    if not service_instance:
        raise Exception("Could not load service instance")

    protection_id = str(uuid.uuid4())
    protection = {
        "Id": protection_id,
        "ResourceArn": service_instance.cloudfront_distribution_arn,
    }
    shield.expect_list_protections([protection])

    health_check_id = service_instance.route53_health_checks[0]["health_check_id"]
    shield.expect_associate_health_check(protection_id, health_check_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert service_instance.shield_associated_health_check == {
        "domain_name": expected_domain_name,
        "health_check_id": health_check_id,
        "protection_id": protection_id,
    }

    shield.assert_no_pending_responses()


def subtest_provision_creates_health_check_alarms(
    tasks,
    cloudwatch_commercial,
    instance_model,
    service_instance_id="4321",
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    tags = service_instance.tags if service_instance.tags else []
    expected_health_check_alarms = []

    for _, health_check in enumerate(service_instance.route53_health_checks):
        health_check_id = health_check["health_check_id"]
        alarm_name = _get_alarm_name(health_check_id)

        cloudwatch_commercial.expect_put_metric_alarm(
            health_check_id, alarm_name, service_instance
        )
        alarm_arn = f"{health_check_id} ARN"
        expected_health_check_alarms.append(
            {
                "alarm_name": alarm_name,
                "health_check_id": health_check_id,
            }
        )

        # wait for alarm
        cloudwatch_commercial.expect_describe_alarms(
            alarm_name, [{"AlarmArn": alarm_arn}]
        )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert (
        service_instance.cloudwatch_health_check_alarms == expected_health_check_alarms
    )

    cloudwatch_commercial.assert_no_pending_responses()


def subtest_provision_creates_sns_notification_topic(
    tasks,
    sns_commercial,
    instance_model,
    service_instance_id="4321",
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    sns_commercial.expect_create_topic(service_instance)

    tasks.run_queued_tasks_and_enqueue_dependents()
    sns_commercial.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert (
        service_instance.sns_notification_topic_arn
        == f"{service_instance.id}-notifications-arn"
    )


def subtest_provision_creates_ddos_detected_alarm(
    tasks,
    cloudwatch_commercial,
    instance_model,
    service_instance_id="4321",
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    alarm_name = generate_ddos_alarm_name(service_instance_id)
    cloudwatch_commercial.expect_put_ddos_detected_alarm(
        alarm_name, service_instance, service_instance.sns_notification_topic_arn
    )
    cloudwatch_commercial.expect_describe_alarms(
        alarm_name, [{"AlarmArn": f"ddos-{service_instance.id}-arn"}]
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    cloudwatch_commercial.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.ddos_detected_cloudwatch_alarm_name == alarm_name


def subtest_provision_subscribes_sns_notification_topic(
    tasks,
    sns_commercial,
    instance_model,
    service_instance_id="4321",
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    sns_commercial.expect_subscribe_topic(
        service_instance.sns_notification_topic_arn,
        service_instance.alarm_notification_email,
        service_instance.id,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    sns_commercial.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert (
        service_instance.sns_notification_topic_subscription_arn
        == f"{service_instance.id}-subscription-arn"
    )
