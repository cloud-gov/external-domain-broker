import pytest  # noqa F401


from broker.extensions import config

from broker.models import CDNDedicatedWAFServiceInstance, DedicatedALB, Operation
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


@pytest.fixture
def dedicated_alb(
    clean_db, dedicated_alb_id, dedicated_alb_arn, service_instance_id, operation_id
):
    dedicated_alb = factories.DedicatedALBFactory.create(
        id=dedicated_alb_id, alb_arn=dedicated_alb_arn, dedicated_org="org-1"
    )

    service_instance = factories.DedicatedALBServiceInstanceFactory.create(
        id=service_instance_id,
        org_id="org-1",
        alb_arn=dedicated_alb_arn,
        alb_listener_arn="listener-1",
    )

    clean_db.session.add(dedicated_alb)
    clean_db.session.add(service_instance)
    clean_db.session.commit()

    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )

    return dedicated_alb


def test_waf_generate_web_acl_name_cdn(service_instance):
    assert (
        waf.generate_web_acl_name(service_instance, "cg-external-domains")
        == f"cg-external-domains-cdn-{service_instance.id}-dedicated-waf"
    )


def test_waf_generate_web_acl_name_alb(clean_db, dedicated_alb_arn):
    dedicated_alb = factories.DedicatedALBFactory.create(
        alb_arn=dedicated_alb_arn, dedicated_org="org-1"
    )
    assert (
        waf.generate_web_acl_name(dedicated_alb, "cg-external-domains")
        == f"cg-external-domains-alb-{dedicated_alb.id}-dedicated-waf"
    )


def test_get_web_acl_rules_errors(clean_db, service_instance_id):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id=service_instance_id
    )
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    with pytest.raises(RuntimeError):
        waf._get_web_acl_rules(service_instance, "acl-1")


def test_get_web_acl_scope_errors(clean_db, service_instance_id):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id=service_instance_id
    )
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    with pytest.raises(RuntimeError):
        waf._get_web_acl_scope(service_instance)


def test_waf_create_web_acl_no_tags(
    clean_db, service_instance_id, service_instance, operation_id, wafv2_commercial
):
    wafv2_commercial.expect_cdn_create_web_acl(
        service_instance.id,
        config.WAF_RATE_LIMIT_RULE_GROUP_ARN,
        service_instance.tags,
    )

    waf.create_cdn_web_acl.call_local(operation_id)

    wafv2_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )
    assert service_instance.dedicated_waf_web_acl_arn
    assert service_instance.dedicated_waf_web_acl_id
    assert service_instance.dedicated_waf_web_acl_name


def test_waf_create_web_acl_unmigrated_cdn_instance(
    clean_db,
    service_instance_id,
    unmigrated_cdn_service_instance_operation_id,
    wafv2_commercial,
):
    operation = clean_db.session.get(
        Operation, unmigrated_cdn_service_instance_operation_id
    )
    service_instance = operation.service_instance

    wafv2_commercial.expect_cdn_create_web_acl(
        service_instance.id,
        config.WAF_RATE_LIMIT_RULE_GROUP_ARN,
        service_instance.tags,
    )

    waf.create_cdn_web_acl.call_local(unmigrated_cdn_service_instance_operation_id)

    wafv2_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )
    assert service_instance.dedicated_waf_web_acl_arn
    assert service_instance.dedicated_waf_web_acl_id
    assert service_instance.dedicated_waf_web_acl_name


def test_waf_create_alb_web_acl(
    clean_db,
    operation_id,
    dedicated_alb_id,
    dedicated_alb,
    wafv2_govcloud,
):
    wafv2_govcloud.expect_alb_create_web_acl(
        dedicated_alb_id,
    )

    waf.create_alb_web_acl.call_local(operation_id)

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )
    assert service_instance.dedicated_waf_web_acl_arn
    assert service_instance.dedicated_waf_web_acl_id
    assert service_instance.dedicated_waf_web_acl_name


def test_waf_create_alb_web_acl_errors_no_dedicated_alb(
    clean_db, operation_id, service_instance_id, wafv2_govcloud, dedicated_alb_arn
):
    service_instance = factories.DedicatedALBServiceInstanceFactory.create(
        id=service_instance_id,
        org_id="org-1",
        alb_arn=dedicated_alb_arn,
        alb_listener_arn="listener-1",
    )

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )

    with pytest.raises(RuntimeError):
        waf.create_alb_web_acl.call_local(operation_id)

    wafv2_govcloud.assert_no_pending_responses()


def test_waf_create_alb_web_acl_returns_early(
    clean_db, operation_id, service_instance_id, wafv2_govcloud, dedicated_alb_arn
):
    dedicated_alb = factories.DedicatedALBFactory.create(
        alb_arn=dedicated_alb_arn,
        dedicated_org="org-1",
        dedicated_waf_web_acl_arn="waf-arn",
        dedicated_waf_web_acl_id="waf-id",
        dedicated_waf_web_acl_name="waf-name",
    )
    service_instance = factories.DedicatedALBServiceInstanceFactory.create(
        id=service_instance_id,
        org_id="org-1",
        alb_arn=dedicated_alb_arn,
        alb_listener_arn="listener-1",
    )

    clean_db.session.add(dedicated_alb)
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )

    waf.create_alb_web_acl.call_local(operation_id)

    wafv2_govcloud.assert_no_pending_responses()


def test_waf_associate_alb_web_acl(
    clean_db,
    operation_id,
    dedicated_alb_id,
    dedicated_alb,
    dedicated_alb_arn,
    waf_web_acl_arn,
    wafv2_govcloud,
):
    dedicated_alb.dedicated_waf_web_acl_arn = waf_web_acl_arn
    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    wafv2_govcloud.expect_alb_associate_web_acl(
        waf_web_acl_arn,
        dedicated_alb_arn,
    )

    waf.associate_alb_web_acl.call_local(operation_id)

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    updated_dedicated_alb = clean_db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )
    assert updated_dedicated_alb.dedicated_waf_associated == True


def test_waf_delete_web_acl_gives_up_after_max_retries(
    clean_db, service_instance_id, service_instance, operation_id, wafv2_commercial
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
        wafv2_commercial.expect_get_web_acl(
            service_instance.dedicated_waf_web_acl_id,
            service_instance.dedicated_waf_web_acl_name,
        )
        wafv2_commercial.expect_delete_web_acl_lock_exception(
            service_instance.dedicated_waf_web_acl_id,
            service_instance.dedicated_waf_web_acl_name,
        )

    with pytest.raises(RuntimeError):
        waf._delete_web_acl_with_retries(operation_id, service_instance)


def test_waf_delete_web_acl_handles_empty_values(
    clean_db, service_instance, operation_id, wafv2_commercial
):
    service_instance.dedicated_waf_web_acl_id = None
    service_instance.dedicated_waf_web_acl_name = None
    service_instance.dedicated_waf_web_acl_arn = None

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    waf.delete_web_acl.call_local(operation_id)
    wafv2_commercial.assert_no_pending_responses()


def test_waf_delete_web_acl_succeeds_on_retry(
    clean_db, service_instance_id, service_instance, operation_id, wafv2_commercial
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

    wafv2_commercial.expect_get_web_acl(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )
    wafv2_commercial.expect_delete_web_acl_lock_exception(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )
    wafv2_commercial.expect_get_web_acl(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )
    wafv2_commercial.expect_delete_web_acl(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )

    waf._delete_web_acl_with_retries(operation_id, service_instance)
    wafv2_commercial.assert_no_pending_responses()


def test_waf_delete_web_acl_unmigrated_cdn_dedicated_waf_instance(
    unmigrated_cdn_dedicated_waf_service_instance_operation_id,
    wafv2_commercial,
):
    waf.delete_web_acl.call_local(
        unmigrated_cdn_dedicated_waf_service_instance_operation_id
    )
    wafv2_commercial.assert_no_pending_responses()


def test_waf_put_logging_configuration_no_arn(
    clean_db, service_instance, operation_id, wafv2_commercial
):
    assert not service_instance.dedicated_waf_web_acl_arn

    waf.put_cdn_waf_logging_configuration.call_local(operation_id)

    wafv2_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()


def test_waf_put_logging_configuration(
    clean_db, service_instance_id, service_instance, operation_id, wafv2_commercial
):
    service_instance.dedicated_waf_web_acl_arn = "1234-dedicated-waf-arn"

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )

    wafv2_commercial.expect_put_logging_configuration(
        service_instance.dedicated_waf_web_acl_arn,
        config.CDN_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    waf.put_cdn_waf_logging_configuration.call_local(operation_id)

    wafv2_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()


def test_waf_put_logging_configuration_unmigrated_cdn_instance(
    clean_db,
    service_instance_id,
    unmigrated_cdn_service_instance_operation_id,
    wafv2_commercial,
):
    operation = clean_db.session.get(
        Operation, unmigrated_cdn_service_instance_operation_id
    )
    service_instance = operation.service_instance

    service_instance.dedicated_waf_web_acl_arn = "1234-dedicated-waf-arn"

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )

    wafv2_commercial.expect_put_logging_configuration(
        service_instance.dedicated_waf_web_acl_arn,
        config.CDN_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    waf.put_cdn_waf_logging_configuration.call_local(
        unmigrated_cdn_service_instance_operation_id
    )

    wafv2_commercial.assert_no_pending_responses()


def test_put_alb_waf_logging_configuration(
    clean_db,
    operation_id,
    dedicated_alb,
    wafv2_govcloud,
):
    dedicated_alb.dedicated_waf_web_acl_arn = "1234-dedicated-waf-arn"

    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    wafv2_govcloud.expect_put_logging_configuration(
        dedicated_alb.dedicated_waf_web_acl_arn,
        config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    waf.put_alb_waf_logging_configuration.call_local(operation_id)

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()
