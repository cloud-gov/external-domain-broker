from datetime import date

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    Challenge,
    Operation,
    CDNServiceInstance,
)

from tests.lib.client import check_last_operation_description


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
    subtest_update_updates_ALIAS_records(tasks, route53)
    subtest_waits_for_dns_changes(tasks, route53)
    subtest_update_removes_certificate_from_iam(tasks, iam_commercial)
    subtest_update_marks_update_complete(tasks)


def subtest_update_creates_private_key_and_csr(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(CDNServiceInstance, "4321")
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
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == "4321"

    instance = db.session.get(CDNServiceInstance, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "new-origin.com"
    assert instance.cloudfront_origin_path == "/somewhere-else"
    return operation_id


def subtest_gets_new_challenges(tasks):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(CDNServiceInstance, "4321")
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
    service_instance = db.session.get(CDNServiceInstance, "4321")
    assert service_instance.route53_change_ids == [bar_com_change_id, foo_com_change_id]


def subtest_update_answers_challenges(tasks, dns):
    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "4321")
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
    service_instance = db.session.get(CDNServiceInstance, "4321")
    certificate = service_instance.new_certificate
    answered = [c.answered for c in certificate.challenges]
    assert answered == [True, True]


def subtest_waits_for_dns_changes(tasks, route53):
    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "4321")

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "4321")
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_update_retrieves_new_cert(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "4321")
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None


def subtest_update_uploads_new_cert(tasks, iam_commercial, simple_regex):
    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "4321")
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
    service_instance = db.session.get(CDNServiceInstance, "4321")
    certificate = service_instance.new_certificate
    assert certificate.iam_server_certificate_name
    assert certificate.iam_server_certificate_name.startswith("4321")
    assert certificate.iam_server_certificate_id
    assert certificate.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert certificate.iam_server_certificate_arn
    assert certificate.iam_server_certificate_arn.startswith("arn:aws:iam")


def subtest_updates_cloudfront(tasks, cloudfront):
    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "4321")
    certificate = service_instance.new_certificate
    id_ = certificate.id
    cloudfront.expect_get_distribution_config(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        bucket_prefix="4321/",
        custom_error_responses={
            "Quantity": 2,
            "Items": [
                {
                    "ErrorCode": 404,
                    "ResponsePagePath": "/errors/404.html",
                    "ResponseCode": "404",
                    "ErrorCachingMinTTL": 300,
                },
                {
                    "ErrorCode": 405,
                    "ResponsePagePath": "/errors/405.html",
                    "ResponseCode": "405",
                    "ErrorCachingMinTTL": 300,
                },
            ],
        },
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
                    "ErrorCachingMinTTL": 300,
                },
                {
                    "ErrorCode": 405,
                    "ResponsePagePath": "/errors/405.html",
                    "ResponseCode": "405",
                    "ErrorCachingMinTTL": 300,
                },
            ],
        },
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()

    service_instance = db.session.get(CDNServiceInstance, "4321")
    cloudfront.assert_no_pending_responses()
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate.id == id_


def subtest_update_waits_for_cloudfront_update(tasks, cloudfront):
    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "4321")
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
    service_instance = db.session.get(CDNServiceInstance, "4321")
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state


def subtest_update_removes_certificate_from_iam(tasks, iam_commercial):
    iam_commercial.expects_delete_server_certificate(
        f"4321-{date.today().isoformat()}-1"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    iam_commercial.assert_no_pending_responses()
    instance = db.session.get(CDNServiceInstance, "4321")
    assert len(instance.certificates) == 1


def subtest_update_same_domains(
    client, dns, tasks, route53, iam_commercial, simple_regex, cloudfront
):
    subtest_update_same_domains_creates_update_operation(client, dns)
    subtest_update_same_domains_does_not_create_new_certificate(tasks)
    subtest_update_same_domains_does_not_create_new_challenges(tasks)
    subtest_update_same_domains_does_not_update_route53(tasks, route53)
    subtest_update_same_domains_does_not_retrieve_new_certificate(tasks)
    subtest_update_same_domains_does_not_update_iam(tasks)
    subtest_update_same_domains_updates_cloudfront(tasks, cloudfront)
    subtest_update_waits_for_cloudfront_update(tasks, cloudfront)
    subtest_update_updates_ALIAS_records(tasks, route53)
    subtest_waits_for_dns_changes(tasks, route53)
    subtest_update_same_domains_does_not_delete_server_certificate(tasks)
    subtest_update_marks_update_complete(tasks)


def subtest_update_same_domains_creates_update_operation(client, dns):
    dns.add_cname("_acme-challenge.foo.com")
    dns.add_cname("_acme-challenge.bar.com")
    client.update_cdn_instance(
        "4321",
        params={
            "domains": "bar.com, Foo.com",
            "origin": "newer-origin.com",
            "error_responses": {},
        },
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == "4321"

    instance = db.session.get(CDNServiceInstance, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "newer-origin.com"
    return operation_id


def subtest_update_same_domains_does_not_create_new_certificate(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(CDNServiceInstance, "4321")
    assert len(instance.certificates) == 1


def subtest_update_same_domains_does_not_create_new_challenges(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(CDNServiceInstance, "4321")
    certificate = instance.new_certificate
    assert len(certificate.challenges.all()) == 2
    assert all([c.answered for c in certificate.challenges])


def subtest_update_same_domains_does_not_update_route53(tasks, route53):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(CDNServiceInstance, "4321")
    assert not instance.route53_change_ids
    # should run wait for changes, which should do nothing
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_update_same_domains_does_not_retrieve_new_certificate(tasks):
    # the idea here is that we don't have new challenges, so asking
    # for a new certificate should raise an error.
    # no errors = did not try to ask for a new certificate
    tasks.run_queued_tasks_and_enqueue_dependents()  # answer_challenges
    tasks.run_queued_tasks_and_enqueue_dependents()  # retrieve_certificate


def subtest_update_same_domains_does_not_update_iam(tasks):
    # if we don't prime IAM to expect a call, then we didn't update iam
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_update_same_domains_updates_cloudfront(tasks, cloudfront):
    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "4321")
    certificate = service_instance.new_certificate
    id_ = certificate.id
    cloudfront.expect_get_distribution_config(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.new_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        bucket_prefix="4321/",
        custom_error_responses={
            "Quantity": 2,
            "Items": [
                {
                    "ErrorCode": 404,
                    "ResponsePagePath": "/errors/404.html",
                    "ResponseCode": "404",
                    "ErrorCachingMinTTL": 300,
                },
                {
                    "ErrorCode": 405,
                    "ResponsePagePath": "/errors/405.html",
                    "ResponseCode": "405",
                    "ErrorCachingMinTTL": 300,
                },
            ],
        },
    )
    cloudfront.expect_update_distribution(
        caller_reference="4321",
        domains=["bar.com", "foo.com"],
        certificate_id=certificate.iam_server_certificate_id,
        origin_hostname="newer-origin.com",
        origin_path="/somewhere-else",
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
        forward_cookie_policy="whitelist",
        forwarded_cookies=["mycookie", "myothercookie", "anewcookie"],
        forwarded_headers=["X-MY-HEADER", "X-YOUR-HEADER"],
        origin_protocol_policy="http-only",
        bucket_prefix="4321/",
        custom_error_responses={"Quantity": 0},
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()

    service_instance = db.session.get(CDNServiceInstance, "4321")
    cloudfront.assert_no_pending_responses()
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate.id == id_


def subtest_update_same_domains_does_not_delete_server_certificate(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(CDNServiceInstance, "4321")
    assert len(instance.certificates) == 1


def subtest_update_updates_ALIAS_records(tasks, route53):
    bar_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "bar.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "fake1234.cloudfront.net"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "4321")
    assert service_instance.route53_change_ids == [bar_com_change_id, foo_com_change_id]
