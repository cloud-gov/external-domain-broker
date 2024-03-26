import json
from datetime import date

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    Challenge,
    Operation,
    DedicatedALBServiceInstance,
    DedicatedALBListener,
)
from broker.tasks.alb import get_lowest_used_alb

from tests.lib.factories import ALBServiceInstanceFactory
from tests.lib.client import check_last_operation_description

from tests.integration.dedicated_alb.test_dedicated_alb_update import (
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


def test_provision_happy_path(
    client, dns, tasks, route53, iam_govcloud, simple_regex, alb
):
    operation_id = subtest_provision_creates_provision_operation(client, dns)
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_provision_creates_LE_user(tasks)
    check_last_operation_description(
        client, "4321", operation_id, "Registering user for Lets Encrypt"
    )
    subtest_provision_creates_private_key_and_csr(tasks)
    check_last_operation_description(
        client, "4321", operation_id, "Creating credentials for Lets Encrypt"
    )
    subtest_provision_initiates_LE_challenge(tasks)
    check_last_operation_description(
        client, "4321", operation_id, "Initiating Lets Encrypt challenges"
    )
    subtest_provision_updates_TXT_records(tasks, route53)
    check_last_operation_description(
        client, "4321", operation_id, "Updating DNS TXT records"
    )
    subtest_provision_waits_for_route53_changes(tasks, route53)
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for DNS changes"
    )
    subtest_provision_answers_challenges(tasks, dns)
    check_last_operation_description(
        client, "4321", operation_id, "Answering Lets Encrypt challenges"
    )
    subtest_provision_retrieves_certificate(tasks)
    check_last_operation_description(
        client, "4321", operation_id, "Retrieving SSL certificate from Lets Encrypt"
    )
    subtest_provision_uploads_certificate_to_iam(tasks, iam_govcloud, simple_regex)
    check_last_operation_description(
        client, "4321", operation_id, "Uploading SSL certificate to AWS"
    )
    subtest_provision_selects_dedicated_alb(tasks, alb)
    check_last_operation_description(
        client, "4321", operation_id, "Selecting load balancer"
    )
    subtest_provision_adds_certificate_to_alb(tasks, alb)
    check_last_operation_description(
        client, "4321", operation_id, "Adding SSL certificate to load balancer"
    )
    subtest_provision_provisions_ALIAS_records(tasks, route53, alb)
    check_last_operation_description(
        client, "4321", operation_id, "Creating DNS ALIAS records"
    )
    subtest_provision_waits_for_route53_changes(tasks, route53)
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for DNS changes"
    )
    subtest_provision_marks_operation_as_succeeded(tasks)
    check_last_operation_description(client, "4321", operation_id, "Complete!")
    subtest_update_happy_path(
        client, dns, tasks, route53, iam_govcloud, simple_regex, alb
    )
    subtest_update_noop(client)


def subtest_provision_creates_provision_operation(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_dedicated_alb_instance(
        "4321", params={"domains": "example.com, Foo.com"}
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Provision"
    assert operation.service_instance_id == "4321"

    instance = db.session.get(
        DedicatedALBServiceInstance, operation.service_instance_id
    )
    assert instance is not None
    assert instance.domain_names == ["example.com", "foo.com"]

    return operation_id


def subtest_provision_creates_LE_user(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    acme_user = service_instance.acme_user
    assert acme_user
    assert "RSA" in acme_user.private_key_pem
    assert "@gsa.gov" in acme_user.email
    assert "localhost:14000" in acme_user.uri
    assert "body" in json.loads(acme_user.registration_json)


def subtest_provision_creates_private_key_and_csr(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    assert "BEGIN PRIVATE KEY" in certificate.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in certificate.csr_pem


def subtest_provision_initiates_LE_challenge(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate

    assert certificate.challenges.count() == 2
    assert certificate.order_json is not None


def subtest_provision_updates_TXT_records(tasks, route53):
    example_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.example.com.domains.cloud.test"
    )
    foo_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.foo.com.domains.cloud.test"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.route53_change_ids == [
        example_com_change_id,
        foo_com_change_id,
    ]


def subtest_provision_waits_for_route53_changes(tasks, route53):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_provision_answers_challenges(tasks, dns):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate

    example_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%example.com")
    ).first()

    foo_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%foo.com")
    ).first()

    dns.add_txt(
        "_acme-challenge.example.com.domains.cloud.test.",
        example_com_challenge.validation_contents,
    )

    dns.add_txt(
        "_acme-challenge.foo.com.domains.cloud.test.",
        foo_com_challenge.validation_contents,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    answered = [c.answered for c in certificate.challenges]
    assert answered == [True, True]


def subtest_provision_retrieves_certificate(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None
    assert json.loads(certificate.order_json)["body"]["status"] == "valid"


def subtest_provision_uploads_certificate_to_iam(tasks, iam_govcloud, simple_regex):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam_govcloud.expect_upload_server_certificate(
        name=f"{service_instance.id}-{today}-{certificate.id}",
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path="/alb/external-domains-test/",
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    assert certificate.iam_server_certificate_name
    assert certificate.iam_server_certificate_name.startswith("4321")
    assert certificate.iam_server_certificate_id
    assert certificate.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert certificate.iam_server_certificate_arn
    assert certificate.iam_server_certificate_arn.startswith("arn:aws:iam")


def subtest_provision_selects_dedicated_alb(tasks, alb):
    our_listener_0 = DedicatedALBListener(
        listener_arn="our-arn-0", dedicated_org="our-org"
    )
    our_listener_1 = DedicatedALBListener(
        listener_arn="our-arn-1", dedicated_org="our-org"
    )
    empty_listener_0 = DedicatedALBListener(listener_arn="empty-arn-0")
    other_listener_0 = DedicatedALBListener(
        listener_arn="other-arn-0", dedicated_org="other-org"
    )
    other_listener_1 = DedicatedALBListener(
        listener_arn="other-arn-1", dedicated_org="other-org"
    )

    db.session.add_all(
        [
            our_listener_0,
            our_listener_1,
            empty_listener_0,
            other_listener_0,
            other_listener_1,
        ]
    )
    db.session.commit()

    db.session.expunge_all()
    alb.expect_get_certificates_for_listener("our-arn-0", 1)
    alb.expect_get_certificates_for_listener("our-arn-1", 5)
    alb.expect_get_listeners("our-arn-0")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.alb_arn.startswith("alb-our-arn-0")


def subtest_provision_adds_certificate_to_alb(tasks, alb):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    id_ = certificate.id
    alb.expect_add_certificate_to_listener(
        "our-arn-0", certificate.iam_server_certificate_arn
    )
    alb.expect_describe_alb("alb-our-arn-0", "alb.cloud.test")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate is not None
    assert service_instance.current_certificate.id == id_


def subtest_provision_provisions_ALIAS_records(tasks, route53, alb):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    example_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "example.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_provision_marks_operation_as_succeeded(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state
