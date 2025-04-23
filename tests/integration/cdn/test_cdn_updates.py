import pytest

from broker.models import CDNServiceInstance
from broker.tasks import cloudfront as cloudfront_tasks

from tests.lib import factories


@pytest.fixture
def cdn_instance_ready_for_update(clean_db):
    """
    a cdn instance that looks like one we'd update.
    We should test in the happy-path test that it looks reasonable/realistic.
    """
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="started-as-cdn-instance",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_distribution_arn="fake-arn",
        cloudfront_origin_hostname="newer-origin.com",
        cloudfront_origin_path="/somewhere-else",
        origin_protocol_policy="https-only",
        forwarded_headers=["HOST"],
    )
    service_instance.new_certificate = factories.CertificateFactory.create(
        id="1",
        service_instance_id="started-as-cdn-instance",
        iam_server_certificate_id="a-certificate-id",
    )
    clean_db.session.add(service_instance)
    clean_db.session.add(service_instance.new_certificate)
    clean_db.session.commit()
    return service_instance


def test_update_with_new_style_response(
    clean_db, cdn_instance_ready_for_update, cloudfront
):
    # create the operation
    service_instance_id = "started-as-cdn-instance"
    operation = factories.OperationFactory.create(
        id="1", service_instance=cdn_instance_ready_for_update, action="Update"
    )
    clean_db.session.add(operation)
    clean_db.session.commit()
    expect_update_domain_names = ["example.com", "foo.com"]
    expect_origin_hostname = "newer-origin.com"
    expect_origin_path = "/somewhere-else"
    expect_forward_cookie_policy = (
        CDNServiceInstance.ForwardCookiePolicy.WHITELIST.value
    )
    expect_origin_protocol_policy = "https-only"
    expect_custom_error_responses = {"Quantity": 0}

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(CDNServiceInstance, service_instance_id)
    certificate = service_instance.new_certificate
    id_ = certificate.id
    cloudfront.expect_get_distribution_config_returning_cache_behavior_id(
        caller_reference=service_instance_id,
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.new_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        bucket_prefix="4321/",
        cache_policy_id="my-cache-policy",
        origin_request_policy_id="my-origin-policy",
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
    cloudfront.expect_update_distribution_with_cache_policy_id(
        caller_reference=service_instance_id,
        domains=expect_update_domain_names,
        certificate_id=certificate.iam_server_certificate_id,
        origin_hostname=expect_origin_hostname,
        origin_path=expect_origin_path,
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
        origin_protocol_policy=expect_origin_protocol_policy,
        bucket_prefix="4321/",
        custom_error_responses=expect_custom_error_responses,
        cache_policy_id="my-cache-policy",
        origin_request_policy_id="my-origin-policy",
    )

    cloudfront.expect_tag_resource(service_instance, service_instance.tags)

    cloudfront_tasks.update_distribution.call_local("1")
    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(CDNServiceInstance, service_instance_id)
    cloudfront.assert_no_pending_responses()
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate.id == id_
