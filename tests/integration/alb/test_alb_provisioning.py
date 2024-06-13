import pytest  # noqa F401

from broker.extensions import db
from broker.models import Operation, ALBServiceInstance
from broker.tasks.alb import get_lowest_used_alb
from tests.lib.client import check_last_operation_description


from tests.lib.cdn.provision import (
    subtest_provision_creates_provision_operation,
    subtest_provision_creates_LE_user,
    subtest_provision_creates_private_key_and_csr,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_answers_challenges,
    subtest_provision_retrieves_certificate,
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_provisions_ALIAS_records,
    subtest_provision_marks_operation_as_succeeded,
)

from tests.integration.alb.test_alb_update import (
    subtest_update_happy_path,
    subtest_update_noop,
)

# The subtests below are "interesting".  Before test_provision_happy_path, we
# had separate tests for each stage in the task pipeline.  But each test would
# have to duplicate much of the previous test.  This was arduous and slow. Now
# we have a single test_provision_happy_path, and many subtest_foo helper
# methods.  This still makes it clear which stage in the task pipeline is
# failing (look for the subtask_foo in the traceback), and allows us to re-use
# these subtasks when testing failure scenarios.


def test_gets_lowest_used_alb(alb):
    alb.expect_get_certificates_for_listener("listener-arn-0", 1)
    alb.expect_get_listeners("listener-arn-0")
    assert get_lowest_used_alb(["listener-arn-0"]) == (
        "alb-listener-arn-0",
        "listener-arn-0",
    )
    alb.expect_get_certificates_for_listener("listener-arn-0", 2)
    alb.expect_get_certificates_for_listener("listener-arn-1", 1)
    alb.expect_get_listeners("listener-arn-1")
    assert get_lowest_used_alb(["listener-arn-0", "listener-arn-1"]) == (
        "alb-listener-arn-1",
        "listener-arn-1",
    )
    alb.expect_get_certificates_for_listener("listener-arn-1", 1)
    alb.expect_get_certificates_for_listener("listener-arn-0", 2)
    alb.expect_get_listeners("listener-arn-1")
    assert get_lowest_used_alb(["listener-arn-1", "listener-arn-0"]) == (
        "alb-listener-arn-1",
        "listener-arn-1",
    )
    alb.expect_get_certificates_for_listener("listener-arn-1", 1)
    alb.expect_get_certificates_for_listener("listener-arn-2", 2)
    alb.expect_get_certificates_for_listener("listener-arn-0", 2)
    alb.expect_get_listeners("listener-arn-1")
    assert get_lowest_used_alb(
        ["listener-arn-1", "listener-arn-2", "listener-arn-0"]
    ) == ("alb-listener-arn-1", "listener-arn-1")
    alb.expect_get_certificates_for_listener("listener-arn-0", 19)
    alb.expect_get_certificates_for_listener("listener-arn-1", 0)
    alb.expect_get_certificates_for_listener("listener-arn-2", 25)
    alb.expect_get_certificates_for_listener("listener-arn-3", 20)
    alb.expect_get_certificates_for_listener("listener-arn-4", 17)
    alb.expect_get_listeners("listener-arn-1")
    assert get_lowest_used_alb(
        [
            "listener-arn-0",
            "listener-arn-1",
            "listener-arn-2",
            "listener-arn-3",
            "listener-arn-4",
        ]
    ) == ("alb-listener-arn-1", "listener-arn-1")


def test_provision_happy_path(
    client, dns, tasks, route53, iam_govcloud, simple_regex, alb
):
    instance_model = ALBServiceInstance
    operation_id = subtest_provision_creates_provision_operation(client, dns)
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_provision_creates_LE_user(tasks, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Registering user for Lets Encrypt"
    )
    subtest_provision_creates_private_key_and_csr(tasks, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Creating credentials for Lets Encrypt"
    )
    subtest_provision_initiates_LE_challenge(tasks, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Initiating Lets Encrypt challenges"
    )
    subtest_provision_updates_TXT_records(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Updating DNS TXT records"
    )
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for DNS changes"
    )
    subtest_provision_answers_challenges(tasks, dns, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Answering Lets Encrypt challenges"
    )
    subtest_provision_retrieves_certificate(tasks, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Retrieving SSL certificate from Lets Encrypt"
    )
    subtest_provision_uploads_certificate_to_iam(
        tasks, iam_govcloud, simple_regex, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Uploading SSL certificate to AWS"
    )
    subtest_provision_selects_alb(tasks, alb)
    check_last_operation_description(
        client, "4321", operation_id, "Selecting load balancer"
    )
    subtest_provision_adds_certificate_to_alb(tasks, alb)
    check_last_operation_description(
        client, "4321", operation_id, "Adding SSL certificate to load balancer"
    )
    subtest_provision_provisions_ALIAS_records(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Creating DNS ALIAS records"
    )
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for DNS changes"
    )
    subtest_provision_marks_operation_as_succeeded(tasks, instance_model)
    check_last_operation_description(client, "4321", operation_id, "Complete!")
    subtest_update_happy_path(
        client, dns, tasks, route53, iam_govcloud, simple_regex, alb
    )
    subtest_update_noop(client)


def subtest_provision_creates_provision_operation(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_alb_instance("4321", params={"domains": "example.com, Foo.com"})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Provision"
    assert operation.service_instance_id == "4321"

    instance = db.session.get(ALBServiceInstance, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["example.com", "foo.com"]

    return operation_id


def subtest_provision_selects_alb(tasks, alb):
    db.session.expunge_all()
    alb.expect_get_certificates_for_listener("listener-arn-0", 1)
    alb.expect_get_certificates_for_listener("listener-arn-1", 5)
    alb.expect_get_listeners("listener-arn-0")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    service_instance = db.session.get(ALBServiceInstance, "4321")
    assert service_instance.alb_arn.startswith("alb-listener-arn-0")


def subtest_provision_adds_certificate_to_alb(tasks, alb):
    db.session.expunge_all()
    service_instance = db.session.get(ALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    id_ = certificate.id
    alb.expect_add_certificate_to_listener(
        "listener-arn-0", certificate.iam_server_certificate_arn
    )
    alb.expect_describe_alb("alb-listener-arn-0", "alb.cloud.test")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(ALBServiceInstance, "4321")
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate is not None
    assert service_instance.current_certificate.id == id_
