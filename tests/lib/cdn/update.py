from datetime import date

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import Operation, CDNServiceInstance

from tests.lib.client import check_last_operation_description
from tests.lib.update import (
    subtest_update_creates_private_key_and_csr,
    subtest_gets_new_challenges,
    subtest_update_updates_TXT_records,
    subtest_update_answers_challenges,
    subtest_waits_for_dns_changes,
    subtest_update_retrieves_new_cert,
    subtest_update_marks_update_complete,
    subtest_update_removes_certificate_from_iam,
    subtest_update_same_domains_does_not_update_iam,
    subtest_update_same_domains_does_not_retrieve_new_certificate,
)


def subtest_update_happy_path(
    client,
    dns,
    tasks,
    route53,
    iam_commercial,
    simple_regex,
    cloudfront,
    instance_model,
):
    operation_id = subtest_update_creates_update_operation(client, dns, instance_model)
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_update_creates_private_key_and_csr(tasks, instance_model)
    subtest_gets_new_challenges(tasks, instance_model)
    subtest_update_updates_TXT_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_answers_challenges(tasks, dns, instance_model)
    subtest_update_retrieves_new_cert(tasks, instance_model)
    subtest_update_uploads_new_cert(tasks, iam_commercial, simple_regex, instance_model)
    subtest_updates_cloudfront(tasks, cloudfront, instance_model)
    subtest_update_waits_for_cloudfront_update(tasks, cloudfront, instance_model)
    subtest_update_updates_ALIAS_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_removes_certificate_from_iam(tasks, iam_commercial, instance_model)
    subtest_update_marks_update_complete(tasks, instance_model)


def subtest_update_creates_update_operation(
    client, dns, instance_model, service_instance_id="4321"
):
    dns.add_cname("_acme-challenge.foo.com")
    dns.add_cname("_acme-challenge.bar.com")
    client.update_instance(
        instance_model,
        service_instance_id,
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
    assert operation.service_instance_id == service_instance_id

    instance = db.session.get(instance_model, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "new-origin.com"
    assert instance.cloudfront_origin_path == "/somewhere-else"
    return operation_id


def subtest_updates_cloudfront(
    tasks, cloudfront, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    certificate = service_instance.new_certificate
    id_ = certificate.id
    cloudfront.expect_get_distribution_config(
        caller_reference=service_instance_id,
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
        caller_reference=service_instance_id,
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

    service_instance = db.session.get(instance_model, service_instance_id)
    cloudfront.assert_no_pending_responses()
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate.id == id_


def subtest_update_waits_for_cloudfront_update(
    tasks, cloudfront, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
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


def subtest_update_same_domains(
    client, dns, tasks, route53, cloudfront, instance_model
):
    subtest_update_same_domains_creates_update_operation(client, dns, instance_model)
    subtest_update_same_domains_does_not_create_new_certificate(tasks, instance_model)
    subtest_update_same_domains_does_not_create_new_challenges(tasks, instance_model)
    subtest_update_same_domains_does_not_update_route53(tasks, route53, instance_model)
    subtest_update_same_domains_does_not_retrieve_new_certificate(tasks)
    subtest_update_same_domains_does_not_update_iam(tasks)
    subtest_update_same_domains_updates_cloudfront(
        tasks,
        cloudfront,
        instance_model,
        expect_update_domain_names=["bar.com", "foo.com"],
    )
    subtest_update_waits_for_cloudfront_update(tasks, cloudfront, instance_model)
    subtest_update_updates_ALIAS_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_same_domains_does_not_delete_server_certificate(
        tasks, instance_model
    )
    subtest_update_marks_update_complete(tasks, instance_model)


def subtest_update_same_domains_creates_update_operation(
    client, dns, instance_model, service_instance_id="4321"
):
    dns.add_cname("_acme-challenge.foo.com")
    dns.add_cname("_acme-challenge.bar.com")
    client.update_instance(
        instance_model,
        service_instance_id,
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
    assert operation.service_instance_id == service_instance_id

    instance = db.session.get(instance_model, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "newer-origin.com"
    return operation_id


def subtest_update_same_domains_does_not_create_new_certificate(
    tasks, instance_model, service_instance_id="4321"
):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(instance_model, service_instance_id)
    assert len(instance.certificates) == 1


def subtest_update_same_domains_does_not_create_new_challenges(
    tasks, instance_model, service_instance_id="4321"
):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(instance_model, service_instance_id)
    certificate = instance.new_certificate
    assert len(certificate.challenges.all()) == 2
    assert all([c.answered for c in certificate.challenges])


def subtest_update_same_domains_does_not_update_route53(
    tasks, route53, instance_model, service_instance_id="4321"
):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(instance_model, service_instance_id)
    assert not instance.route53_change_ids
    # should run wait for changes, which should do nothing
    tasks.run_queued_tasks_and_enqueue_dependents()
    route53.assert_no_pending_responses()


def subtest_update_same_domains_updates_cloudfront(
    tasks,
    cloudfront,
    instance_model,
    service_instance_id="4321",
    expect_update_domain_names=None,
    expect_forwarded_headers=None,
    expect_forwarded_cookies=None,
    expect_origin_hostname=None,
    expect_origin_path=None,
    expect_forward_cookie_policy=None,
    expect_origin_protocol_policy=None,
    expect_custom_error_responses=None,
):
    if expect_update_domain_names is None:
        expect_update_domain_names = ["example.com", "foo.com"]
    if expect_forwarded_headers is None:
        expect_forwarded_headers = ["X-MY-HEADER", "X-YOUR-HEADER"]
    if expect_forwarded_cookies is None:
        expect_forwarded_cookies = ["mycookie", "myothercookie", "anewcookie"]
    if expect_origin_hostname is None:
        expect_origin_hostname = "newer-origin.com"
    if expect_origin_path is None:
        expect_origin_path = "/somewhere-else"
    if expect_forward_cookie_policy is None:
        expect_forward_cookie_policy = (
            CDNServiceInstance.ForwardCookiePolicy.WHITELIST.value
        )
    if expect_origin_protocol_policy is None:
        expect_origin_protocol_policy = "http-only"
    if expect_custom_error_responses is None:
        expect_custom_error_responses = {"Quantity": 0}

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    certificate = service_instance.new_certificate
    id_ = certificate.id
    cloudfront.expect_get_distribution_config(
        caller_reference=service_instance_id,
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
        caller_reference=service_instance_id,
        domains=expect_update_domain_names,
        certificate_id=certificate.iam_server_certificate_id,
        origin_hostname=expect_origin_hostname,
        origin_path=expect_origin_path,
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
        forward_cookie_policy=expect_forward_cookie_policy,
        forwarded_cookies=expect_forwarded_cookies,
        forwarded_headers=expect_forwarded_headers,
        origin_protocol_policy=expect_origin_protocol_policy,
        bucket_prefix="4321/",
        custom_error_responses=expect_custom_error_responses,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()

    service_instance = db.session.get(instance_model, service_instance_id)
    cloudfront.assert_no_pending_responses()
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate.id == id_


def subtest_update_same_domains_does_not_delete_server_certificate(
    tasks, instance_model, service_instance_id="4321"
):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(instance_model, service_instance_id)
    assert len(instance.certificates) == 1


def subtest_update_updates_ALIAS_records(
    tasks,
    route53,
    instance_model,
    service_instance_id="4321",
    expected_domains=["bar.com", "foo.com"],
    hosted_zone_id="fake1234.cloudfront.net",
):
    change_ids = []
    for domain in expected_domains:
        change_id = route53.expect_create_ALIAS_and_return_change_id(
            f"{domain}.{config.DNS_ROOT_DOMAIN}", hosted_zone_id
        )
        change_ids.append(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()
    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert service_instance.route53_change_ids.sort() == change_ids.sort()


def subtest_update_uploads_new_cert(
    tasks, iam_commercial, simple_regex, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
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
    service_instance = db.session.get(instance_model, service_instance_id)
    certificate = service_instance.new_certificate
    assert certificate.iam_server_certificate_name
    assert certificate.iam_server_certificate_name.startswith(service_instance_id)
    assert certificate.iam_server_certificate_id
    assert certificate.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert certificate.iam_server_certificate_arn
    assert certificate.iam_server_certificate_arn.startswith("arn:aws:iam")
