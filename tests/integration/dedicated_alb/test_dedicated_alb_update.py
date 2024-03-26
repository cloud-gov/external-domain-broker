import json
from datetime import date, datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    Challenge,
    Operation,
    DedicatedALBServiceInstance,
    DedicatedALBListener,
)
from broker.tasks.huey import huey
from broker.tasks.letsencrypt import create_user, generate_private_key

from tests.lib import factories
from tests.lib.client import check_last_operation_description


@pytest.fixture
def service_instance(clean_db):
    service_instance = factories.DedicatedALBServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        alb_arn="our-arn-1",
        alb_listener_arn="alb-our-arn-1",
        domain_internal="fake1234.cloud.test",
        org_id="our-org",
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_arn="certificate_arn",
        iam_server_certificate_name="certificate_name",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1001,
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=1001,
        answered=True,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=1001,
        answered=True,
    )
    service_instance.current_certificate = current_cert
    db.session.add(service_instance)
    db.session.add(current_cert)
    db.session.commit()
    db.session.expunge_all()
    return service_instance


def test_refuses_to_update_synchronously(client):
    client.update_dedicated_alb_instance("4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_update_synchronously_by_default(client):
    client.update_dedicated_alb_instance("4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_update_with_duplicate_domains(client, dns, service_instance):
    factories.DedicatedALBServiceInstanceFactory.create(
        domain_names=["foo.com", "bar.com"]
    )
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.update_dedicated_alb_instance(
        "4321", params={"domains": "example.com, foo.com"}
    )

    assert "already exists" in client.response.body, client.response.body
    assert client.response.status_code == 400, client.response.body


def test_duplicate_domain_check_ignores_self(client, dns, service_instance):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.update_dedicated_alb_instance(
        "4321", params={"domains": "example.com, foo.com"}
    )

    assert client.response.status_code == 200, client.response.body


def test_duplicate_domain_check_ignores_deactivated(client, dns, service_instance):
    factories.DedicatedALBServiceInstanceFactory.create(
        domain_names="foo.com", deactivated_at=datetime.utcnow()
    )
    dns.add_cname("_acme-challenge.foo.com")

    client.update_dedicated_alb_instance("4321", params={"domains": "foo.com"})

    assert client.response.status_code == 202, client.response.body


def test_refuses_to_update_without_any_acme_challenge_CNAMEs(client, service_instance):
    client.update_dedicated_alb_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com " in desc
    assert "_acme-challenge.foo.com.domains.cloud.test" in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_update_without_one_acme_challenge_CNAME(
    client, dns, service_instance
):
    dns.add_cname("_acme-challenge.foo.com")
    client.update_dedicated_alb_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com" not in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_update_with_incorrect_acme_challenge_CNAME(
    client, dns, service_instance
):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com", target="INCORRECT")
    client.update_dedicated_alb_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")

    assert "is set incorrectly" in desc

    assert " _acme-challenge.foo.com " in desc
    assert " _acme-challenge.foo.com.domains.cloud.test" in desc
    assert " INCORRECT" in desc

    assert " _acme-challenge.bar.com" not in desc
    assert client.response.status_code == 400


def test_refuses_update_for_canceled_instance(client, dns, clean_db, service_instance):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    service_instance.deactivated_at = datetime.now()
    db.session.add(service_instance)
    db.session.commit()

    client.update_dedicated_alb_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "canceled" in desc
    assert client.response.status_code == 400


def test_refuses_update_for_nonexistent_instance(client, dns):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.update_dedicated_alb_instance("4321", params={"domains": "bar.com,foo.com"})
    desc = client.response.json.get("description")
    assert "does not exist" in desc
    assert client.response.status_code == 400


def test_refuses_update_for_instance_with_operation(client, dns, service_instance):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    factories.OperationFactory.create(service_instance=service_instance)
    client.update_dedicated_alb_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")

    assert "in progress" in desc
    assert client.response.status_code == 400


def subtest_update_happy_path(
    client, dns, tasks, route53, iam_govcloud, simple_regex, alb
):
    operation_id = subtest_update_creates_update_operation(client, dns)
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_update_creates_private_key_and_csr(tasks)
    subtest_gets_new_challenges(tasks)
    subtest_update_updates_TXT_records(tasks, route53)
    subtest_waits_for_dns_changes(tasks, route53)
    subtest_update_answers_challenges(tasks, dns)
    subtest_update_retrieves_new_cert(tasks)
    subtest_update_uploads_new_cert(tasks, iam_govcloud, simple_regex)
    subtest_update_selects_alb(tasks, alb)
    subtest_update_adds_certificate_to_alb(tasks, alb)
    subtest_update_provisions_ALIAS_records(tasks, route53, alb)
    subtest_waits_for_dns_changes(tasks, route53)
    subtest_update_removes_certificate_from_alb(tasks, alb)
    subtest_update_removes_certificate_from_iam(tasks, iam_govcloud)
    subtest_update_marks_update_complete(tasks)


def subtest_update_creates_private_key_and_csr(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    assert "BEGIN PRIVATE KEY" in certificate.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in certificate.csr_pem


def subtest_update_creates_update_operation(client, dns):
    dns.add_cname("_acme-challenge.foo.com")
    dns.add_cname("_acme-challenge.bar.com")
    client.update_dedicated_alb_instance("4321", params={"domains": "bar.com, Foo.com"})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == "4321"

    instance = db.session.get(
        DedicatedALBServiceInstance, operation.service_instance_id
    )
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    return operation_id


def subtest_gets_new_challenges(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate

    assert certificate.challenges.count() == 2
    assert sorted(certificate.subject_alternative_names) == sorted(
        ["bar.com", "foo.com"]
    )


def subtest_update_updates_TXT_records(tasks, route53):
    bar_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.bar.com.domains.cloud.test"
    )
    foo_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.foo.com.domains.cloud.test"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.route53_change_ids == [bar_com_change_id, foo_com_change_id]


def subtest_update_answers_challenges(tasks, dns):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate

    bar_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%bar.com"), Challenge.answered.is_(False)
    ).first()

    foo_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%foo.com"), Challenge.answered.is_(False)
    ).first()

    dns.add_txt(
        "_acme-challenge.bar.com.domains.cloud.test.",
        bar_com_challenge.validation_contents,
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


def subtest_waits_for_dns_changes(tasks, route53):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_update_retrieves_new_cert(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None


def subtest_update_uploads_new_cert(tasks, iam_commercial, simple_regex):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam_commercial.expect_upload_server_certificate(
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


def subtest_update_selects_alb(tasks, alb):
    db.session.expunge_all()
    alb.expect_get_certificates_for_listener("our-arn-0", 1)
    alb.expect_get_certificates_for_listener("our-arn-1", 5)
    alb.expect_get_listeners("our-arn-0")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.alb_arn.startswith("alb-our-arn-0")


def subtest_update_adds_certificate_to_alb(tasks, alb):
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


def subtest_update_provisions_ALIAS_records(tasks, route53, alb):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    example_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "bar.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_update_marks_update_complete(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state


def subtest_update_removes_certificate_from_alb(tasks, alb):
    alb.expect_remove_certificate_from_listener(
        "our-arn-0",
        f"arn:aws:iam::000000000000:server-certificate/alb/external-domains-test/4321-{date.today().isoformat()}-1",
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    alb.assert_no_pending_responses()


def subtest_update_removes_certificate_from_iam(tasks, iam_govcloud):
    iam_govcloud.expects_delete_server_certificate(f"4321-{date.today().isoformat()}-1")

    tasks.run_queued_tasks_and_enqueue_dependents()

    iam_govcloud.assert_no_pending_responses()
    instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert len(instance.certificates) == 1


def subtest_update_noop(client):
    client.update_dedicated_alb_instance("4321", params={"domains": "bar.com, Foo.com"})
    assert client.response.status_code == 200
