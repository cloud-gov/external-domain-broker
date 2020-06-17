import json
from datetime import date, datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import Challenge, Operation, ALBServiceInstance
from tests.lib.factories import ALBServiceInstanceFactory

# The subtests below are "interesting".  Before test_provision_happy_path, we
# had separate tests for each stage in the task pipeline.  But each test would
# have to duplicate much of the previous test.  This was arduous and slow. Now
# we have a single test_provision_happy_path, and many subtest_foo helper
# methods.  This still makes it clear which stage in the task pipeline is
# failing (look for the subtask_foo in the traceback), and allows us to re-use
# these subtasks when testing failure scenarios.


def test_refuses_to_provision_synchronously(client):
    client.provision_alb_instance("4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_synchronously_by_default(client):
    client.provision_alb_instance("4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_without_domains(client):
    client.provision_cdn_instance("4321")

    assert "domains" in client.response.body
    assert client.response.status_code == 400


def test_refuses_to_provision_with_duplicate_domains(client, dns):
    ALBServiceInstanceFactory.create(domain_names=["foo.com", "bar.com"])
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.provision_cdn_instance("4321", params={"domains": "example.com, foo.com"})

    assert "already exists" in client.response.body, client.response.body
    assert client.response.status_code == 400, client.response.body


def test_duplicate_domain_check_ignores_deactivated(client, dns):
    ALBServiceInstanceFactory.create(
        domain_names="foo.com", deactivated_at=datetime.utcnow()
    )
    dns.add_cname("_acme-challenge.foo.com")

    client.provision_cdn_instance("4321", params={"domains": "foo.com"})

    assert client.response.status_code == 202, client.response.body


def test_refuses_to_provision_without_any_acme_challenge_CNAMEs(client):
    client.provision_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com " in desc
    assert "_acme-challenge.foo.com.domains.cloud.test" in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_provision_without_one_acme_challenge_CNAME(client, dns):
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com" not in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_provision_with_incorrect_acme_challenge_CNAME(client, dns):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com", target="INCORRECT")
    client.provision_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")

    assert "is set incorrectly" in desc

    assert " _acme-challenge.foo.com " in desc
    assert " _acme-challenge.foo.com.domains.cloud.test" in desc
    assert " INCORRECT" in desc

    assert " _acme-challenge.bar.com" not in desc
    assert client.response.status_code == 400


def test_provision_happy_path(client, dns, tasks, route53, iam_govcloud, simple_regex, alb):
    subtest_provision_creates_provision_operation(client, dns)
    subtest_provision_creates_LE_user(tasks)
    subtest_provision_creates_private_key_and_csr(tasks)
    subtest_provision_initiates_LE_challenge(tasks)
    subtest_provision_updates_TXT_records(tasks, route53)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_answers_challenges(tasks, dns)
    subtest_provision_retrieves_certificate(tasks)
    subtest_provision_uploads_certificate_to_iam(tasks, iam_govcloud, simple_regex)
    subtest_provision_adds_certificate_to_alb(tasks, alb)
    subtest_provision_provisions_ALIAS_records(tasks, route53, alb)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_marks_operation_as_succeeded(tasks)


def subtest_provision_creates_provision_operation(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_alb_instance("4321", params={"domains": "example.com, Foo.com"})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Provision"
    assert operation.service_instance_id == "4321"

    instance = ALBServiceInstance.query.get(operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["example.com", "foo.com"]


def subtest_provision_creates_LE_user(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = ALBServiceInstance.query.get("4321")
    acme_user = service_instance.acme_user
    assert acme_user
    assert "RSA" in acme_user.private_key_pem
    assert "@gsa.gov" in acme_user.email
    assert "localhost:14000" in acme_user.uri
    assert "body" in json.loads(acme_user.registration_json)


def subtest_provision_creates_private_key_and_csr(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = ALBServiceInstance.query.get("4321")
    assert "BEGIN PRIVATE KEY" in service_instance.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in service_instance.csr_pem


def subtest_provision_initiates_LE_challenge(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = ALBServiceInstance.query.get("4321")

    assert service_instance.challenges.count() == 2


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
    service_instance = ALBServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == [
        example_com_change_id,
        foo_com_change_id,
    ]


def subtest_provision_waits_for_route53_changes(tasks, route53):
    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("4321")

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_provision_answers_challenges(tasks, dns):
    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("4321")

    example_com_challenge = service_instance.challenges.filter(
        Challenge.domain.like("%example.com")
    ).first()

    foo_com_challenge = service_instance.challenges.filter(
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
    service_instance = ALBServiceInstance.query.get("4321")
    answered = [c.answered for c in service_instance.challenges]
    assert answered == [True, True]


def subtest_provision_retrieves_certificate(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("4321")

    assert 1 == service_instance.fullchain_pem.count("BEGIN CERTIFICATE")
    assert 1 == service_instance.cert_pem.count("BEGIN CERTIFICATE")


def subtest_provision_uploads_certificate_to_iam(tasks, iam_govcloud, simple_regex):
    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("4321")
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam_govcloud.expect_upload_server_certificate(
        name=f"{service_instance.id}-{today}",
        cert=service_instance.cert_pem,
        private_key=service_instance.private_key_pem,
        chain=service_instance.fullchain_pem,
        path = "/alb/external-domains-test/"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("4321")
    assert service_instance.iam_server_certificate_name
    assert service_instance.iam_server_certificate_name.startswith("4321")
    assert service_instance.iam_server_certificate_id
    assert service_instance.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert service_instance.iam_server_certificate_arn
    assert service_instance.iam_server_certificate_arn.startswith("arn:aws:iam")


def subtest_provision_adds_certificate_to_alb(tasks, alb):
    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("4321")
    alb.expect_happy_path_add_certificate_to_listener(
        "alb-arn-0", service_instance.iam_server_certificate_arn
    )
    alb.expect_describe_alb("alb-arn-0", "alb.cloud.test")
    tasks.run_queued_tasks_and_enqueue_dependents()
    service_instance = ALBServiceInstance.query.get("4321")
    alb.assert_no_pending_responses()
    assert service_instance.alb_arn.startswith("alb-arn-")


def subtest_provision_provisions_ALIAS_records(tasks, route53, alb):
    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("4321")
    example_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "example.com.domains.cloud.test", "alb.cloud.test"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "alb.cloud.test"
    )
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_provision_marks_operation_as_succeeded(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("4321")
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state
