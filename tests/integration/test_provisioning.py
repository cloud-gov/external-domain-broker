import pytest  # noqa F401
import json
from datetime import date

from openbrokerapi.service_broker import OperationState

from broker.extensions import db
from broker.models import Operation, ServiceInstance, Challenge


def test_refuses_to_provision_synchronously(client):
    client.provision_instance("4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_synchronously_by_default(client):
    client.provision_instance("4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_without_domains(client):
    client.provision_instance("4321")

    assert "domains" in client.response.body
    assert client.response.status_code == 400


def test_refuses_to_provision_without_any_acme_challenge_CNAMEs(client):
    client.provision_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com " in desc
    assert "_acme-challenge.foo.com.domains.cloud.test" in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_provision_without_one_acme_challenge_CNAME(client, dns):
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com" not in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_provision_with_incorrect_acme_challenge_CNAME(client, dns):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com", target="INCORRECT")
    client.provision_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")

    assert "is set incorrectly" in desc

    assert " _acme-challenge.foo.com " in desc
    assert " _acme-challenge.foo.com.domains.cloud.test" in desc
    assert " INCORRECT" in desc

    assert " _acme-challenge.bar.com" not in desc
    assert client.response.status_code == 400


def subtest_provision_creates_provision_operation(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_instance("4321", params={"domains": "example.com, Foo.com"})

    assert "AsyncRequired" not in client.response.body
    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == OperationState.IN_PROGRESS
    assert operation.service_instance_id == "4321"

    instance = ServiceInstance.query.get(operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["example.com", "foo.com"]


def subtest_provision_creates_LE_user(tasks):
    db.session.expunge_all()
    tasks.run_pipeline_stages(1)

    service_instance = ServiceInstance.query.get("4321")
    acme_user = service_instance.acme_user
    assert acme_user
    assert "RSA" in acme_user.private_key_pem
    assert "@gsa.gov" in acme_user.email
    assert "localhost:14000" in acme_user.uri
    assert "body" in json.loads(acme_user.registration_json)


def subtest_provision_creates_private_key_and_csr(tasks):
    db.session.expunge_all()
    tasks.run_pipeline_stages(1)

    service_instance = ServiceInstance.query.get("4321")
    assert "BEGIN PRIVATE KEY" in service_instance.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in service_instance.csr_pem


def subtest_provision_initiates_LE_challenge(tasks):
    db.session.expunge_all()
    tasks.run_pipeline_stages(1)

    service_instance = ServiceInstance.query.get("4321")

    assert service_instance.challenges.count() == 2


def subtest_provision_updates_TXT_records(tasks, route53):
    example_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.example.com.domains.cloud.test"
    )
    foo_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.foo.com.domains.cloud.test"
    )

    tasks.run_pipeline_stages(1)

    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == [
        example_com_change_id,
        foo_com_change_id,
    ]


def subtest_provision_waits_for_route53_changes(tasks, route53):
    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_pipeline_stages(1)

    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_provision_ansers_challenges(tasks, dns):
    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")

    example_com_challenge = service_instance.challenges.filter(
        Challenge.domain.like("%example.com")
    ).first()

    foo_com_challenge = service_instance.challenges.filter(
        Challenge.domain.like("%foo.com")
    ).first()

    dns.add_txt(
        f"_acme-challenge.example.com.domains.cloud.test.",
        f"{example_com_challenge.validation_contents}",
    )

    dns.add_txt(
        f"_acme-challenge.foo.com.domains.cloud.test.",
        f"{foo_com_challenge.validation_contents}",
    )

    tasks.run_pipeline_stages(1)

    answered = [c.answered for c in service_instance.challenges]
    assert answered == [True, True]


def subtest_provision_retrieves_certificate(tasks):
    tasks.run_pipeline_stages(1)

    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")

    assert 2 == service_instance.fullchain_pem.count("BEGIN CERTIFICATE")
    assert 1 == service_instance.cert_pem.count("BEGIN CERTIFICATE")


def subtest_provision_uploads_certificate_to_iam(tasks, iam, simple_regex):
    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam.expect_certificate_upload(
        name=f"{service_instance.id}-{today}",
        cert=service_instance.cert_pem,
        private_key=service_instance.private_key_pem,
        chain=service_instance.fullchain_pem,
    )

    tasks.run_pipeline_stages(1)

    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")
    assert service_instance.iam_server_certificate_id
    assert service_instance.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert service_instance.iam_server_certificate_arn
    assert service_instance.iam_server_certificate_arn.startswith("arn:aws:iam")


def subtest_provision_creates_cloudfront_distribution(tasks, cloudfront):
    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")

    cloudfront.expect_create_distribution(
        service_instance=service_instance,
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
    )

    tasks.run_pipeline_stages(1)

    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")

    assert service_instance.cloudfront_distribution_arn
    assert service_instance.cloudfront_distribution_arn.startswith("arn:aws:cloudfront")
    assert service_instance.cloudfront_distribution_arn.endswith("FakeDistributionId")
    assert service_instance.cloudfront_distribution_id == "FakeDistributionId"
    assert service_instance.cloudfront_distribution_url == "fake1234.cloudfront.net"


def subtest_provision_waits_for_cloudfront_distribution(tasks, cloudfront):
    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")

    cloudfront.expect_wait_for_distribution(
        service_instance=service_instance, distribution_id="FakeDistributionId"
    )

    tasks.run_pipeline_stages(1)


def subtest_provision_provisions_ALIAS_record(tasks, route53):
    example_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "example.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "fake1234.cloudfront.net"
    )

    tasks.run_pipeline_stages(1)

    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == [
        example_com_change_id,
        foo_com_change_id,
    ]


def subtest_provision_marks_operation_as_succeeded(client, tasks):
    tasks.run_pipeline_stages(1)
    db.session.expunge_all()
    service_instance = ServiceInstance.query.get("4321")
    operation = service_instance.operations.first()
    assert operation
    assert operation.States.SUCCEEDED == operation.state


def test_provision_happy_path(
    client, dns, tasks, route53, iam, simple_regex, cloudfront
):
    subtest_provision_creates_provision_operation(client, dns)
    subtest_provision_creates_LE_user(tasks)
    subtest_provision_creates_private_key_and_csr(tasks)
    subtest_provision_initiates_LE_challenge(tasks)
    subtest_provision_updates_TXT_records(tasks, route53)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_ansers_challenges(tasks, dns)
    subtest_provision_retrieves_certificate(tasks)
    subtest_provision_uploads_certificate_to_iam(tasks, iam, simple_regex)
    subtest_provision_creates_cloudfront_distribution(tasks, cloudfront)
    subtest_provision_waits_for_cloudfront_distribution(tasks, cloudfront)
    subtest_provision_provisions_ALIAS_record(tasks, route53)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_marks_operation_as_succeeded(client, tasks)

