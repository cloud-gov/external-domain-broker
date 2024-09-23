import pytest  # noqa F401
import uuid

from broker.extensions import db
from broker.tasks.cloudwatch import _get_alarm_name


def subtest_update_web_acl_does_not_update(tasks, wafv2):
    tasks.run_queued_tasks_and_enqueue_dependents()

    # Nothing should get updated since the domains have not changed
    wafv2.assert_no_pending_responses()


def subtest_update_creates_new_health_checks(
    tasks, route53, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    route53.expect_create_health_check(service_instance.id, "bar.com", 0)
    route53.expect_change_tags_for_resource("bar.com", service_instance.tags)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert sorted(
        service_instance.route53_health_checks,
        key=lambda check: check["domain_name"],
    ) == [
        {
            "domain_name": "bar.com",
            "health_check_id": "bar.com ID",
        },
        {
            "domain_name": "example.com",
            "health_check_id": "example.com ID",
        },
        {"domain_name": "foo.com", "health_check_id": "foo.com ID"},
    ]

    route53.assert_no_pending_responses()


def subtest_update_deletes_unused_health_checks(
    tasks, route53, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    delete_health_check = [
        check
        for check in service_instance.route53_health_checks
        if check["domain_name"] == "example.com"
    ][0]
    route53.expect_delete_health_check(delete_health_check["health_check_id"])

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert sorted(
        service_instance.route53_health_checks,
        key=lambda check: check["domain_name"],
    ) == [
        {
            "domain_name": "bar.com",
            "health_check_id": "bar.com ID",
        },
        {"domain_name": "foo.com", "health_check_id": "foo.com ID"},
    ]

    route53.assert_no_pending_responses()


def subtest_updates_health_checks_do_not_change(tasks, route53, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")

    health_checks_pre_update = service_instance.route53_health_checks

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.route53_health_checks == health_checks_pre_update


def subtest_updates_associated_health_check(
    tasks, shield, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    if not service_instance:
        raise Exception("Could not load service instance")

    # get protection ID from initial creation
    protection_id = service_instance.shield_associated_health_check["protection_id"]

    shield.expect_disassociate_health_check(protection_id, "example.com ID")

    protection_id = str(uuid.uuid4())
    protection = {
        "Id": protection_id,
        "ResourceArn": service_instance.cloudfront_distribution_arn,
    }
    shield.expect_list_protections([protection])
    shield.expect_associate_health_check(protection_id, "bar.com ID")

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert service_instance.shield_associated_health_check == {
        "health_check_id": "bar.com ID",
        "protection_id": protection_id,
        "domain_name": "bar.com",
    }
    shield.assert_no_pending_responses()


def subtest_updates_associated_health_check_no_change(tasks, shield, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    if not service_instance:
        raise Exception("Could not load service instance")

    check_pre_update = service_instance.shield_associated_health_check

    tasks.run_queued_tasks_and_enqueue_dependents()
    shield.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.shield_associated_health_check == check_pre_update


def subtest_update_deletes_health_check_alarms(
    tasks,
    cloudwatch_commercial,
    instance_model,
    expect_delete_health_check_ids,
    service_instance_id="4321",
):
    expect_delete_alarm_names = [
        _get_alarm_name(expect_delete_health_check_id)
        for expect_delete_health_check_id in expect_delete_health_check_ids
    ]
    cloudwatch_commercial.expect_delete_alarms(expect_delete_alarm_names)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.cloudwatch_health_check_alarms == []

    cloudwatch_commercial.assert_no_pending_responses()


def subtest_update_creates_health_check_alarms(
    tasks,
    cloudwatch_commercial,
    instance_model,
    service_instance_id="4321",
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    expect_create_health_check_ids = ["bar.com ID", "foo.com ID"]
    for expect_create_health_check_id in expect_create_health_check_ids:
        cloudwatch_commercial.expect_put_metric_alarm(
            expect_create_health_check_id,
            _get_alarm_name(expect_create_health_check_id),
            service_instance,
        )
        cloudwatch_commercial.expect_describe_alarms(
            _get_alarm_name(expect_create_health_check_id),
            [{"AlarmArn": f"{expect_create_health_check_id} ARN"}],
        )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert sorted(
        service_instance.cloudwatch_health_check_alarms,
        key=lambda alarm: alarm["health_check_id"],
    ) == sorted(
        [
            {
                "health_check_id": "foo.com ID",
                "alarm_name": _get_alarm_name("foo.com ID"),
            },
            {
                "health_check_id": "bar.com ID",
                "alarm_name": _get_alarm_name("bar.com ID"),
            },
        ],
        key=lambda alarm: alarm["health_check_id"],
    )

    cloudwatch_commercial.assert_no_pending_responses()


def subtest_update_does_not_create_sns_notification_topic(
    tasks,
    sns_commercial,
    instance_model,
    service_instance_id="4321",
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.sns_notification_topic_arn

    tasks.run_queued_tasks_and_enqueue_dependents()
    sns_commercial.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.sns_notification_topic_arn


def subtest_update_does_not_create_ddos_cloudwatch_alarm(
    tasks,
    cloudwatch_commercial,
    instance_model,
    service_instance_id="4321",
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.ddos_detected_cloudwatch_alarm_name

    tasks.run_queued_tasks_and_enqueue_dependents()
    cloudwatch_commercial.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.ddos_detected_cloudwatch_alarm_name


def subtest_update_does_not_subscribe_sns_notification_topic(
    tasks,
    sns_commercial,
    instance_model,
    service_instance_id="4321",
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    subscription_arn = service_instance.sns_notification_topic_subscription_arn
    assert subscription_arn is not None

    tasks.run_queued_tasks_and_enqueue_dependents()
    sns_commercial.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.sns_notification_topic_subscription_arn == subscription_arn
