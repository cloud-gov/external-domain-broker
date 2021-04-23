import pytest
from broker.models import CDNServiceInstance

from tests.lib import factories
from tests.lib.client import check_last_operation_description
from tests.integration.cdn.test_cdn_provisioning import (
    subtest_provision_creates_LE_user,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_provisions_ALIAS_records,
    subtest_provision_updates_TXT_records,
    subtest_provision_answers_challenges,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_marks_operation_as_succeeded,
)
from tests.integration.cdn.test_cdn_update import (
    subtest_update_creates_private_key_and_csr,
)
from tests.integration.cdn.test_cdn_renewals import (
    subtest_renew_retrieves_certificate,
    subtest_renewal_removes_certificate_from_iam,
    subtest_updates_certificate_in_cloudfront,
)


@pytest.fixture
def migration_instance(clean_db):
    service_instance = factories.MigrationServiceInstanceFactory.create(
        id="4321", domain_names=["example.com", "foo.com"]
    )
    return service_instance


@pytest.fixture
def full_update_example():
    # this one is used for the full pipeline test.
    # it's kinda finicky because we are reusing other tests that assume some inputs
    params = {}
    params["origin"] = "origin_hostname"
    params["path"] = "origin_path"
    params["forwarded_cookies"] = ["my-cookie", "my-other-cookie"]
    params["forward_cookie_policy"] = "whitelist"
    params["forwarded_headers"] = ["my-header", "my-other-header"]
    params["insecure_origin"] = False
    params["error_responses"] = {"404": "/404.html"}
    params["cloudfront_distribution_id"] = "FakeDistributionId"
    params["cloudfront_distribution_arn"] = "arn:aws:whatever"
    params["iam_server_certificate_id"] = "my-cert-id"
    params["iam_server_certificate_arn"] = "arn:aws:certificate"
    params["iam_server_certificate_name"] = "certificate_name"
    params["domain_internal"] = "fake1234.cloudfront.net"
    return params


@pytest.mark.parametrize(
    "missing_param",
    [
        "origin",
        "path",
        "forwarded_cookies",
        "forward_cookie_policy",
        "forwarded_headers",
        "insecure_origin",
        "error_responses",
        "cloudfront_distribution_id",
        "cloudfront_distribution_arn",
        "iam_server_certificate_name",
        "iam_server_certificate_id",
        "iam_server_certificate_arn",
        "domain_internal",
    ],
)
def test_migration_update_fails_without_required_params(
    client, migration_instance, missing_param, full_update_example
):
    full_update_example.pop(missing_param)
    client.update_instance_to_cdn("4321", params=full_update_example)
    assert client.response.status_code >= 400
    assert "missing" in client.response.json.get("description").lower()
    assert missing_param in client.response.json.get("description")


def test_migration_update_updates_cdn_instance_with_all_fields(
    client, migration_instance, full_update_example, clean_db
):
    client.update_instance_to_cdn("4321", params=full_update_example)
    assert client.response.status_code == 202
    clean_db.session.expunge_all()
    instance = CDNServiceInstance.query.get("4321")
    assert instance.cloudfront_origin_hostname == "origin_hostname"
    assert instance.cloudfront_origin_path == "origin_path"
    assert instance.forwarded_cookies == ["my-cookie", "my-other-cookie"]
    assert instance.forward_cookie_policy == "whitelist"
    assert instance.forwarded_headers == ["my-header", "my-other-header"]
    assert instance.origin_protocol_policy == "https-only"
    assert instance.error_responses == {"404": "/404.html"}
    assert instance.cloudfront_distribution_id == "FakeDistributionId"
    assert instance.cloudfront_distribution_arn == "arn:aws:whatever"
    assert instance.domain_internal == "fake1234.cloudfront.net"


def test_migration_creates_certificate_record(
    client, migration_instance, full_update_example, clean_db
):
    client.update_instance_to_cdn("4321", params=full_update_example)
    assert client.response.status_code == 202
    clean_db.session.expunge_all()
    instance = CDNServiceInstance.query.get("4321")
    assert instance.current_certificate is not None
    assert instance.current_certificate.iam_server_certificate_id == "my-cert-id"
    assert (
        instance.current_certificate.iam_server_certificate_arn == "arn:aws:certificate"
    )
    assert (
        instance.current_certificate.iam_server_certificate_name == "certificate_name"
    )


def test_migration_pipeline(
    clean_db,
    client,
    tasks,
    migration_instance,
    cloudfront,
    route53,
    dns,
    iam_commercial,
    simple_regex,
    full_update_example,
):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.update_instance_to_cdn("4321", params=full_update_example)
    subtest_removes_s3_bucket(tasks, cloudfront, clean_db)
    subtest_adds_logging(tasks, cloudfront, clean_db)
    subtest_provision_creates_LE_user(tasks)
    subtest_update_creates_private_key_and_csr(tasks)
    subtest_provision_initiates_LE_challenge(tasks)
    subtest_provision_provisions_ALIAS_records(tasks, route53)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_updates_TXT_records(tasks, route53)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_answers_challenges(tasks, dns)
    subtest_renew_retrieves_certificate(tasks)
    subtest_provision_uploads_certificate_to_iam(tasks, iam_commercial, simple_regex)
    subtest_updates_certificate_in_cloudfront(tasks, cloudfront)
    subtest_renewal_removes_certificate_from_iam(tasks, iam_commercial)
    subtest_provision_marks_operation_as_succeeded(tasks)


def subtest_removes_s3_bucket(tasks, cloudfront, db):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    cloudfront.expect_get_distribution_config(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        include_le_bucket=True,
    )
    cloudfront.expect_update_distribution(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        distribution_hostname="example.cloudfront.net",
    )
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_adds_logging(tasks, cloudfront, db):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    cloudfront.expect_get_distribution_config(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        include_log_bucket=False,
    )
    cloudfront.expect_update_distribution(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        distribution_hostname="example.cloudfront.net",
        bucket_prefix="4321/",
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
