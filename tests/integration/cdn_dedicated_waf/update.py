import pytest  # noqa F401

from broker.extensions import db


def subtest_update_web_acl_does_not_update(tasks, wafv2):
    tasks.run_queued_tasks_and_enqueue_dependents()

    # Nothing should get updated since the domains have not changed
    wafv2.assert_no_pending_responses()


def subtest_updates_health_checks(
    tasks, route53, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    route53.expect_create_health_check(service_instance.id, "bar.com", 0)
    route53.expect_change_tags_for_resource("bar.com", service_instance.tags)

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
    protection_id = service_instance.shield_associated_health_checks[0]["protection_id"]

    shield.expect_associate_health_check(protection_id, "bar.com ID")
    shield.expect_disassociate_health_check(protection_id, "example.com ID")

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert sorted(
        service_instance.shield_associated_health_checks,
        key=lambda check: check["health_check_id"],
    ) == [
        {
            "health_check_id": "bar.com ID",
            "protection_id": protection_id,
        },
        {
            "health_check_id": "foo.com ID",
            "protection_id": protection_id,
        },
    ]
    shield.assert_no_pending_responses()


def subtest_updates_associated_health_check_no_change(tasks, shield, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    if not service_instance:
        raise Exception("Could not load service instance")

    checks_pre_update = service_instance.shield_associated_health_checks

    tasks.run_queued_tasks_and_enqueue_dependents()
    shield.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.shield_associated_health_checks == checks_pre_update
