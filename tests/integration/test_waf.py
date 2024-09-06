import pytest  # noqa F401

from broker.extensions import db, config

from broker.models import CDNDedicatedWAFServiceInstance, Operation
from broker.tasks import waf
from tests.lib import factories


@pytest.fixture
def service_instance(
    clean_db,
    operation_id,
    service_instance_id,
    cloudfront_distribution_arn,
    protection_id,
):
    service_instance = factories.CDNDedicatedWAFServiceInstanceFactory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_distribution_arn=cloudfront_distribution_arn,
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
        forwarded_headers=["HOST"],
        route53_health_checks=[
            {
                "domain_name": "example.com",
                "health_check_id": "example.com ID",
            },
            {
                "domain_name": "foo.com",
                "health_check_id": "foo.com ID",
            },
        ],
        shield_associated_health_check={
            "domain_name": "example.com",
            "protection_id": protection_id,
            "health_check_id": "fake-health-check-id",
        },
    )
    new_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1002,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
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
    clean_db.session.add(service_instance)
    clean_db.session.add(current_cert)
    clean_db.session.add(new_cert)
    clean_db.session.commit()
    clean_db.session.expunge_all()
    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )
    return service_instance


def test_waf_create_web_acl_no_tags(
    clean_db, service_instance_id, service_instance, operation_id, wafv2
):
    wafv2.expect_create_web_acl(
        service_instance.id,
        config.WAF_RATE_LIMIT_RULE_GROUP_ARN,
        service_instance.tags,
    )

    waf.create_web_acl.call_local(operation_id)

    wafv2.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )
    assert service_instance.dedicated_waf_web_acl_arn


def test_waf_delete_web_acl_gives_up_after_max_retries(
    clean_db, service_instance_id, service_instance, operation_id, wafv2
):
    service_instance.dedicated_waf_web_acl_id = "1234-dedicated-waf-id"
    service_instance.dedicated_waf_web_acl_name = "1234-dedicated-waf"
    service_instance.dedicated_waf_web_acl_arn = "1234-dedicated-waf-arn"

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )

    for i in range(10):
        wafv2.expect_get_web_acl(
            service_instance.dedicated_waf_web_acl_id,
            service_instance.dedicated_waf_web_acl_name,
        )
        wafv2.expect_delete_web_acl_lock_exception(
            service_instance.dedicated_waf_web_acl_id,
            service_instance.dedicated_waf_web_acl_name,
        )

    with pytest.raises(RuntimeError):
        waf._delete_web_acl_with_retries(operation_id, service_instance)


def test_waf_delete_web_acl_succeeds_on_retry(
    clean_db, service_instance_id, service_instance, operation_id, wafv2
):
    service_instance.dedicated_waf_web_acl_id = "1234-dedicated-waf-id"
    service_instance.dedicated_waf_web_acl_name = "1234-dedicated-waf"
    service_instance.dedicated_waf_web_acl_arn = "1234-dedicated-waf-arn"

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )

    wafv2.expect_get_web_acl(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )
    wafv2.expect_delete_web_acl_lock_exception(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )
    wafv2.expect_get_web_acl(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )
    wafv2.expect_delete_web_acl(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )

    waf._delete_web_acl_with_retries(operation_id, service_instance)
    wafv2.assert_no_pending_responses()
