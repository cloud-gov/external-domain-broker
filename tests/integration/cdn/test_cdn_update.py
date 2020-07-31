import json
from datetime import date, datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import Challenge, Operation, CDNServiceInstance
from broker.tasks.huey import huey
from broker.tasks.letsencrypt import create_user, generate_private_key

from tests.lib import factories
from tests.lib.client import check_last_operation_description


@pytest.fixture
def service_instance():
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
    )
    new_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1002,
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
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=1002,
        answered=False,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=1002,
        answered=False,
    )
    service_instance.current_certificate = current_cert
    service_instance.new_certificate = new_cert
    db.session.add(service_instance)
    db.session.add(current_cert)
    db.session.add(new_cert)
    db.session.commit()
    db.session.expunge_all()
    return service_instance


def test_refuses_to_update_synchronously(client):
    client.update_cdn_instance("4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_update_synchronously_by_default(client):
    client.update_cdn_instance("4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_update_with_duplicate_domains(client, dns, service_instance):
    factories.CDNServiceInstanceFactory.create(domain_names=["foo.com", "bar.com"])
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.update_cdn_instance("4321", params={"domains": "example.com, foo.com"})

    assert "already exists" in client.response.body, client.response.body
    assert client.response.status_code == 400, client.response.body


def test_duplicate_domain_check_ignores_self(client, dns, service_instance):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.update_cdn_instance("4321", params={"domains": "example.com, foo.com"})

    assert client.response.status_code == 202, client.response.body


def test_duplicate_domain_check_ignores_deactivated(client, dns, service_instance):
    factories.CDNServiceInstanceFactory.create(
        domain_names="foo.com", deactivated_at=datetime.utcnow()
    )
    dns.add_cname("_acme-challenge.foo.com")

    client.update_cdn_instance("4321", params={"domains": "foo.com"})

    assert client.response.status_code == 202, client.response.body


def test_refuses_to_update_without_any_acme_challenge_CNAMEs(client, service_instance):
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

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
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

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
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

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

    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "canceled" in desc
    assert client.response.status_code == 400


def test_refuses_update_for_nonexistent_instance(client, dns):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})
    desc = client.response.json.get("description")
    assert "does not exist" in desc
    assert client.response.status_code == 400


def test_refuses_update_for_instance_with_operation(client, dns, service_instance):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    factories.OperationFactory.create(service_instance=service_instance)
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")

    assert "in progress" in desc
    assert client.response.status_code == 400


def test_provision_sets_default_origin_if_provided_as_none(
    client, dns, service_instance
):
    client.update_cdn_instance("4321", params={"origin": None})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = CDNServiceInstance.query.get("4321")
    assert config.DEFAULT_CLOUDFRONT_ORIGIN == "cloud.local"
    assert instance.cloudfront_origin_hostname == "cloud.local"

    # make sure nothing else got changed
    assert instance.cloudfront_origin_path == "origin_path"
    assert sorted(instance.domain_names) == sorted(["foo.com", "example.com"])
    assert "HOST" in instance.forwarded_headers


def test_provision_sets_default_origin_path_if_provided_as_none(
    client, dns, service_instance
):
    client.update_cdn_instance("4321", params={"path": None})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = CDNServiceInstance.query.get("4321")
    assert instance.cloudfront_origin_path == ""

    # make sure nothing else got changed
    assert instance.cloudfront_origin_hostname == "origin_hostname"
    assert sorted(instance.domain_names) == sorted(["foo.com", "example.com"])


def test_update_sets_default_cookie_policy_if_provided_as_none(
    client, dns, service_instance
):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()

    client.update_cdn_instance("4321", params={"forward_cookies": None})
    db.session.expunge_all()
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


def test_update_sets_none_cookie_policy(client, dns, service_instance):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()
    client.update_cdn_instance("4321", params={"forward_cookies": ""})
    db.session.expunge_all()
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "none"
    assert instance.forwarded_cookies == []


def test_update_sets_forward_cookie_policy_with_cookies(client, dns, service_instance):
    client.update_cdn_instance(
        "4321", params={"forward_cookies": "my_cookie , my_other_cookie"}
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "whitelist"
    assert instance.forwarded_cookies == ["my_cookie", "my_other_cookie"]


def test_update_sets_forward_cookie_policy_with_star(client, dns, service_instance):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()
    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance(
        "4321", params={"domains": "example.com", "forward_cookies": "*"}
    )
    db.session.expunge_all()
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


def test_update_sets_forward_headers_to_host_when_specified_as_none(
    client, dns, service_instance
):
    service_instance.cloudfront_origin_hostname = config.DEFAULT_CLOUDFRONT_ORIGIN
    service_instance.cloudfront_origin_path = ""
    service_instance.forwarded_headers = ["HOST", "x-my-header"]
    db.session.add(service_instance)
    db.session.commit()

    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance("4321", params={"forward_headers": None})
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forwarded_headers == ["HOST"]


def test_update_sets_forward_headers_plus_host_when_some_specified(
    client, dns, service_instance
):
    service_instance.cloudfront_origin_hostname = config.DEFAULT_CLOUDFRONT_ORIGIN
    service_instance.cloudfront_origin_path = ""
    service_instance.forwarded_headers = ["HOST"]
    db.session.add(service_instance)
    db.session.commit()

    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance(
        "4321", params={"forward_headers": "x-my-header,x-your-header"}
    )
    instance = CDNServiceInstance.query.get("4321")
    assert sorted(instance.forwarded_headers) == sorted(
        ["HOST", "x-my-header", "x-your-header"]
    )


def test_update_does_not_set_host_header_when_using_custom_origin(
    client, dns, service_instance
):
    dns.add_cname("_acme-challenge.example.com")
    service_instance.forwarded_headers = ["x-my-header"]
    db.session.add(service_instance)
    db.session.commit()

    client.update_cdn_instance("4321", params={"forward_headers": None})
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forwarded_headers == []


def test_update_sets_http_when_set(client, dns, service_instance):
    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance(
        "4321", params={"origin": "origin.gov", "insecure_origin": True}
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.origin_protocol_policy == "http-only"


def test_update_refuses_insecure_origin_for_default_origin(
    client, dns, service_instance
):
    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance("4321", params={"origin": None, "insecure_origin": True})
    desc = client.response.json.get("description")
    assert client.response.status_code == 400
    assert "insecure_origin" in desc


def subtest_update_happy_path(
    client, dns, tasks, route53, iam_commercial, simple_regex, cloudfront
):
    operation_id = subtest_update_creates_update_operation(client, dns)
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_update_creates_private_key_and_csr(tasks)
    subtest_gets_new_challenges(tasks)
    subtest_update_updates_TXT_records(tasks, route53)
    subtest_waits_for_dns_changes(tasks, route53)
    subtest_update_answers_challenges(tasks, dns)
    subtest_update_retrieves_new_cert(tasks)
    subtest_update_uploads_new_cert(tasks, iam_commercial, simple_regex)
    subtest_updates_cloudfront(tasks, cloudfront)
    subtest_update_waits_for_cloudfront_update(tasks, cloudfront)
    subtest_update_marks_update_complete(tasks)


def subtest_update_creates_private_key_and_csr(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.new_certificate
    assert "BEGIN PRIVATE KEY" in certificate.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in certificate.csr_pem
    assert len(service_instance.certificates) == 2
    assert service_instance.current_certificate is not None
    assert service_instance.new_certificate is not None
    assert (
        service_instance.current_certificate.id != service_instance.new_certificate.id
    )


def subtest_update_creates_update_operation(client, dns):
    dns.add_cname("_acme-challenge.foo.com")
    dns.add_cname("_acme-challenge.bar.com")
    client.update_cdn_instance(
        "4321",
        params={
            "domains": "bar.com, Foo.com",
            "origin": "new-origin.com",
            "path": "/somewhere-else",
            "forward_cookies": "mycookie,myothercookie, anewcookie",
            "forward_headers": "x-my-header, x-your-header   ",
            "insecure_origin": True,
        },
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == "4321"

    instance = CDNServiceInstance.query.get(operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "new-origin.com"
    assert instance.cloudfront_origin_path == "/somewhere-else"
    return operation_id


def subtest_gets_new_challenges(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.new_certificate

    assert len(certificate.challenges.all()) == 2
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
    service_instance = CDNServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == [bar_com_change_id, foo_com_change_id]


def subtest_update_answers_challenges(tasks, dns):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
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
    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.new_certificate
    answered = [c.answered for c in certificate.challenges]
    assert answered == [True, True]


def subtest_waits_for_dns_changes(tasks, route53):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_update_retrieves_new_cert(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None


def subtest_update_uploads_new_cert(tasks, iam_commercial, simple_regex):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.new_certificate
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam_commercial.expect_upload_server_certificate(
        name=f"{service_instance.id}-{today}-{certificate.id}",
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path="/cloudfront/external-domains-test/",
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.new_certificate
    assert certificate.iam_server_certificate_name
    assert certificate.iam_server_certificate_name.startswith("4321")
    assert certificate.iam_server_certificate_id
    assert certificate.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert certificate.iam_server_certificate_arn
    assert certificate.iam_server_certificate_arn.startswith("arn:aws:iam")


def subtest_updates_cloudfront(tasks, cloudfront):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.new_certificate
    id_ = certificate.id
    cloudfront.expect_get_distribution_config(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
    )
    cloudfront.expect_update_distribution(
        caller_reference="4321",
        domains=["bar.com", "foo.com"],
        certificate_id=certificate.iam_server_certificate_id,
        origin_hostname="new-origin.com",
        origin_path="/somewhere-else",
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
        forward_cookie_policy="whitelist",
        forwarded_cookies=["mycookie", "myothercookie", "anewcookie"],
        forwarded_headers=["x-my-header", "x-your-header"],
        origin_protocol_policy="http-only",
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()

    service_instance = CDNServiceInstance.query.get("4321")
    cloudfront.assert_no_pending_responses()
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate.id == id_


def subtest_update_waits_for_cloudfront_update(tasks, cloudfront):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.current_certificate

    cloudfront.expect_get_distribution(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id="FakeDistributionId",
        status="InProgress",
    )
    cloudfront.expect_get_distribution(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id="FakeDistributionId",
        status="Deployed",
    )

    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_update_marks_update_complete(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state
