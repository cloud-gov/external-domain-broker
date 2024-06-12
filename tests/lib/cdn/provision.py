import json
from datetime import date

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    Challenge,
    Operation,
)


def subtest_provision_creates_provision_operation(client, dns, instance_model):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_instance(
        instance_model,
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
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Provision"
    assert operation.service_instance_id == "4321"

    instance = db.session.get(instance_model, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["example.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "origin.com"
    assert instance.cloudfront_origin_path == "/somewhere"

    client.get_last_operation("4321", operation_id)
    assert "description" in client.response.json
    assert client.response.json.get("description") == "Queuing tasks"
    return operation_id


def subtest_provision_creates_LE_user(tasks, instance_model):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(instance_model, "4321")
    acme_user = service_instance.acme_user
    assert acme_user
    assert "RSA" in acme_user.private_key_pem
    assert "@gsa.gov" in acme_user.email
    assert "localhost:14000" in acme_user.uri
    assert "body" in json.loads(acme_user.registration_json)


def subtest_provision_creates_private_key_and_csr(tasks, instance_model):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(instance_model, "4321")
    assert len(service_instance.certificates) == 1

    assert "BEGIN PRIVATE KEY" in service_instance.new_certificate.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in service_instance.new_certificate.csr_pem


def subtest_provision_initiates_LE_challenge(tasks, instance_model):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(instance_model, "4321")

    assert service_instance.new_certificate.challenges.count() == 2
    assert service_instance.new_certificate.order_json is not None


def subtest_provision_updates_TXT_records(tasks, route53, instance_model):
    example_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.example.com.domains.cloud.test"
    )
    foo_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.foo.com.domains.cloud.test"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.route53_change_ids == [
        example_com_change_id,
        foo_com_change_id,
    ]


def subtest_provision_waits_for_route53_changes(tasks, route53, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_provision_answers_challenges(tasks, dns, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
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
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate
    answered = [c.answered for c in certificate.challenges]
    assert answered == [True, True]


def subtest_provision_retrieves_certificate(tasks, instance_model):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")

    assert len(service_instance.certificates) == 1
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None


def subtest_provision_uploads_certificate_to_iam(
    tasks, iam_commercial, simple_regex, instance_model
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
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
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate
    assert certificate.iam_server_certificate_name
    assert certificate.iam_server_certificate_name.startswith("4321")
    assert certificate.iam_server_certificate_id
    assert certificate.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert certificate.iam_server_certificate_arn
    assert certificate.iam_server_certificate_arn.startswith("arn:aws:iam")


def subtest_provision_creates_cloudfront_distribution(
    tasks, cloudfront, instance_model
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
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
    service_instance = db.session.get(instance_model, "4321")

    assert service_instance.cloudfront_distribution_arn
    assert service_instance.cloudfront_distribution_arn.startswith("arn:aws:cloudfront")
    assert service_instance.cloudfront_distribution_arn.endswith("FakeDistributionId")
    assert service_instance.cloudfront_distribution_id == "FakeDistributionId"
    assert service_instance.domain_internal == "fake1234.cloudfront.net"
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate is not None
    assert service_instance.current_certificate.id == id_


def subtest_provision_waits_for_cloudfront_distribution(
    tasks, cloudfront, instance_model
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
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


def subtest_provision_provisions_ALIAS_records(tasks, route53, instance_model):
    example_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "example.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "fake1234.cloudfront.net"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.route53_change_ids == [
        example_com_change_id,
        foo_com_change_id,
    ]


def subtest_provision_marks_operation_as_succeeded(tasks, instance_model):
    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state
