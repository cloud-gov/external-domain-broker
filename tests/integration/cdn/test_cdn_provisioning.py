import json
from datetime import date, datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import Challenge, Operation, CDNServiceInstance
from tests.lib.factories import CDNServiceInstanceFactory
from tests.lib.client import check_last_operation_description

from tests.integration.cdn.test_cdn_update import (
    subtest_update_happy_path,
    subtest_update_same_domains,
)

# The subtests below are "interesting".  Before test_provision_happy_path, we
# had separate tests for each stage in the task pipeline.  But each test would
# have to duplicate much of the previous test.  This was arduous and slow. Now
# we have a single test_provision_happy_path, and many subtest_foo helper
# methods.  This still makes it clear which stage in the task pipeline is
# failing (look for the subtask_foo in the traceback), and allows us to re-use
# these subtasks when testing failure scenarios.


def test_refuses_to_provision_synchronously(client):
    client.provision_cdn_instance("4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_synchronously_by_default(client):
    client.provision_cdn_instance("4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_without_domains(client):
    client.provision_cdn_instance("4321")

    assert "domains" in client.response.body
    assert client.response.status_code == 400


def test_refuses_to_provision_with_duplicate_domains(client, dns):
    CDNServiceInstanceFactory.create(domain_names=["foo.com", "bar.com"])
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.provision_cdn_instance("4321", params={"domains": "example.com, foo.com"})

    assert "already exists" in client.response.body, client.response.body
    assert client.response.status_code == 400, client.response.body


def test_duplicate_domain_check_ignores_deactivated(client, dns):
    CDNServiceInstanceFactory.create(
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


def test_provision_sets_default_origin_and_path_if_none_provided(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance("4321", params={"domains": "example.com"})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = CDNServiceInstance.query.get("4321")
    assert config.DEFAULT_CLOUDFRONT_ORIGIN == "cloud.local"
    assert instance.cloudfront_origin_hostname == "cloud.local"
    assert instance.cloudfront_origin_path == ""


def test_provision_sets_default_cookie_policy_if_none_provided(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance("4321", params={"domains": "example.com"})
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


def test_provision_sets_none_cookie_policy(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance(
        "4321", params={"domains": "example.com", "forward_cookies": ""}
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "none"
    assert instance.forwarded_cookies == []


def test_provision_sets_forward_cookie_policy_with_cookies(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance(
        "4321",
        params={
            "domains": "example.com",
            "forward_cookies": "my_cookie , my_other_cookie",
        },
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "whitelist"
    assert instance.forwarded_cookies == ["my_cookie", "my_other_cookie"]


def test_provision_sets_forward_cookie_policy_with_star(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance(
        "4321", params={"domains": "example.com", "forward_cookies": "*"}
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


def test_provision_sets_forward_headers_to_host_when_none_specified(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance("4321", params={"domains": "example.com"})
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forwarded_headers == ["HOST"]


def test_provision_sets_forward_headers_plus_host_when_some_specified(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance(
        "4321",
        params={
            "domains": "example.com",
            "forward_headers": "x-my-header,x-your-header",
        },
    )
    instance = CDNServiceInstance.query.get("4321")
    assert sorted(instance.forwarded_headers) == sorted(
        ["HOST", "X-MY-HEADER", "X-YOUR-HEADER"]
    )


def test_provision_does_not_set_host_header_when_using_custom_origin(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance(
        "4321", params={"domains": "example.com", "origin": "my-origin.example.gov"}
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forwarded_headers == []


def test_provision_sets_https_only_by_default(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance("4321", params={"domains": "example.com"})
    instance = CDNServiceInstance.query.get("4321")
    assert instance.origin_protocol_policy == "https-only"


def test_provision_sets_http_when_set(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance(
        "4321",
        params={
            "domains": "example.com",
            "origin": "origin.gov",
            "insecure_origin": True,
        },
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.origin_protocol_policy == "http-only"


def test_provision_refuses_insecure_origin_for_default_origin(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance(
        "4321", params={"domains": "example.com", "insecure_origin": True}
    )
    desc = client.response.json.get("description")
    assert "insecure_origin" in desc
    assert client.response.status_code == 400


def test_provision_sets_custom_error_responses(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_cdn_instance(
        "4321",
        params={
            "domains": "example.com",
            "error_responses": {"404": "/errors/404.html"},
        },
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.error_responses["404"] == "/errors/404.html"


def test_provision_happy_path(
    client, dns, tasks, route53, iam_commercial, simple_regex, cloudfront
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
    subtest_provision_uploads_certificate_to_iam(tasks, iam_commercial, simple_regex)
    check_last_operation_description(
        client, "4321", operation_id, "Uploading SSL certificate to AWS"
    )
    subtest_provision_creates_cloudfront_distribution(tasks, cloudfront)
    check_last_operation_description(
        client, "4321", operation_id, "Creating CloudFront distribution"
    )
    subtest_provision_waits_for_cloudfront_distribution(tasks, cloudfront)
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for CloudFront distribution"
    )
    subtest_provision_provisions_ALIAS_records(tasks, route53)
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
        client, dns, tasks, route53, iam_commercial, simple_regex, cloudfront
    )
    subtest_update_same_domains(
        client, dns, tasks, route53, iam_commercial, simple_regex, cloudfront
    )


def subtest_provision_creates_provision_operation(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_cdn_instance(
        "4321",
        params={
            "domains": "example.com, Foo.com",
            "origin": "origin.com",
            "path": "/somewhere",
            "forward_cookies": "mycookie,myothercookie",
            "forward_headers": "x-my-header, x-your-header   ",
            "insecure_origin": True,
            "error_responses": {"404": "/errors/404.html", "405": "/errors/405.html"},
        },
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Provision"
    assert operation.service_instance_id == "4321"

    instance = CDNServiceInstance.query.get(operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["example.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "origin.com"
    assert instance.cloudfront_origin_path == "/somewhere"

    client.get_last_operation("4321", operation_id)
    assert "description" in client.response.json
    assert client.response.json.get("description") == "Queuing tasks"
    return operation_id


def subtest_provision_creates_LE_user(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = CDNServiceInstance.query.get("4321")
    acme_user = service_instance.acme_user
    assert acme_user
    assert "RSA" in acme_user.private_key_pem
    assert "@gsa.gov" in acme_user.email
    assert "localhost:14000" in acme_user.uri
    assert "body" in json.loads(acme_user.registration_json)


def subtest_provision_creates_private_key_and_csr(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = CDNServiceInstance.query.get("4321")
    assert len(service_instance.certificates) == 1

    assert "BEGIN PRIVATE KEY" in service_instance.new_certificate.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in service_instance.new_certificate.csr_pem


def subtest_provision_initiates_LE_challenge(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = CDNServiceInstance.query.get("4321")

    assert service_instance.new_certificate.challenges.count() == 2
    assert service_instance.new_certificate.order_json is not None


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
    service_instance = CDNServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == [
        example_com_change_id,
        foo_com_change_id,
    ]


def subtest_provision_waits_for_route53_changes(tasks, route53):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_provision_answers_challenges(tasks, dns):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
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
    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.new_certificate
    answered = [c.answered for c in certificate.challenges]
    assert answered == [True, True]


def subtest_provision_retrieves_certificate(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")

    assert len(service_instance.certificates) == 1
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None


def subtest_provision_uploads_certificate_to_iam(tasks, iam_commercial, simple_regex):
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


def subtest_provision_creates_cloudfront_distribution(tasks, cloudfront):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    certificate = service_instance.new_certificate

    id_ = certificate.id

    cloudfront.expect_create_distribution(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
        forward_cookie_policy="whitelist",
        forwarded_cookies=["mycookie", "myothercookie"],
        forwarded_headers=["X-MY-HEADER", "X-YOUR-HEADER"],
        origin_protocol_policy="http-only",
        bucket_prefix="4321/",
        custom_error_responses={
            "Quantity": 2,
            "Items": [
                {
                    "ErrorCode": 404,
                    "ResponsePagePath": "/errors/404.html",
                    "ResponseCode": "404",
                },
                {
                    "ErrorCode": 405,
                    "ResponsePagePath": "/errors/405.html",
                    "ResponseCode": "405",
                },
            ],
        },
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")

    assert service_instance.cloudfront_distribution_arn
    assert service_instance.cloudfront_distribution_arn.startswith("arn:aws:cloudfront")
    assert service_instance.cloudfront_distribution_arn.endswith("FakeDistributionId")
    assert service_instance.cloudfront_distribution_id == "FakeDistributionId"
    assert service_instance.domain_internal == "fake1234.cloudfront.net"
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate is not None
    assert service_instance.current_certificate.id == id_


def subtest_provision_waits_for_cloudfront_distribution(tasks, cloudfront):
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


def subtest_provision_provisions_ALIAS_records(tasks, route53):
    example_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "example.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "fake1234.cloudfront.net"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    assert service_instance.route53_change_ids == [
        example_com_change_id,
        foo_com_change_id,
    ]


def subtest_provision_marks_operation_as_succeeded(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state
