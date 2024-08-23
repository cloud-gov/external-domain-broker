from datetime import date
import pytest  # noqa F401

from broker.extensions import db
from broker.models import (
    CDNServiceInstance,
    Operation,
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
)

from tests.lib.client import check_last_operation_description
from tests.lib.provision import (
    subtest_provision_creates_LE_user,
    subtest_provision_creates_private_key_and_csr,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_answers_challenges,
    subtest_provision_marks_operation_as_succeeded,
)
from tests.lib.tags import sort_instance_tags


def subtest_provision_cdn_instance(
    client,
    dns,
    tasks,
    route53,
    iam_commercial,
    simple_regex,
    cloudfront,
    organization_guid,
    space_guid,
):
    instance_model = CDNServiceInstance
    operation_id = subtest_provision_creates_provision_operation(
        client, dns, organization_guid, space_guid, instance_model
    )
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
        tasks, iam_commercial, simple_regex, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Uploading SSL certificate to AWS"
    )
    subtest_provision_creates_cloudfront_distribution(tasks, cloudfront, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Creating CloudFront distribution"
    )
    subtest_provision_waits_for_cloudfront_distribution(
        tasks, cloudfront, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for CloudFront distribution"
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


def subtest_provision_creates_provision_operation(
    client, dns, organization_guid, space_guid, instance_model
):
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
        organization_guid=organization_guid,
        space_guid=space_guid,
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

    if instance_model == CDNServiceInstance:
        service_plan_name = "domain-with-cdn"
    elif instance_model == CDNDedicatedWAFServiceInstance:
        service_plan_name = "domain-with-cdn-dedicated-waf"
    assert sort_instance_tags(instance.tags) == sort_instance_tags(
        [
            {"Key": "client", "Value": "Cloud Foundry"},
            {"Key": "broker", "Value": "External domain broker"},
            {"Key": "environment", "Value": "test"},
            {"Key": "Service offering name", "Value": "external-domain"},
            {"Key": "Service plan name", "Value": service_plan_name},
            {"Key": "Instance GUID", "Value": "4321"},
            {"Key": "Organization GUID", "Value": organization_guid},
            {"Key": "Space GUID", "Value": space_guid},
            {"Key": "Space name", "Value": "space-1234"},
            {"Key": "Organization name", "Value": "org-1234"},
        ]
    )

    client.get_last_operation("4321", operation_id)
    assert "description" in client.response.json
    assert client.response.json.get("description") == "Queuing tasks"
    return operation_id


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
    tags = service_instance.tags if service_instance.tags else []
    iam_commercial.expect_tag_server_certificate(
        f"{service_instance.id}-{today}-{certificate.id}",
        tags,
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


def subtest_provision_creates_cloudfront_distribution(
    tasks, cloudfront, instance_model
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate

    id_ = certificate.id

    dedicated_waf_web_acl_arn = None
    if instance_model == CDNDedicatedWAFServiceInstance:
        dedicated_waf_web_acl_arn = service_instance.dedicated_waf_web_acl_arn

    cloudfront.expect_create_distribution_with_tags(
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
        dedicated_waf_web_acl_arn=dedicated_waf_web_acl_arn,
        tags=service_instance.tags,
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
    assert service_instance.tags is not None


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


def subtest_provision_retrieves_certificate(tasks, instance_model):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")

    assert len(service_instance.certificates) == 1
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None
