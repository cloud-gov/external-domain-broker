import pytest  # noqa F401
import uuid

from broker.extensions import db

from broker.models import CDNDedicatedWAFServiceInstance, Operation
from broker.tasks import waf
from tests.lib import factories


@pytest.fixture
def protection_id():
    return str(uuid.uuid4())


@pytest.fixture
def service_instance(no_context_clean_db, no_context_app, protection_id):
    with no_context_app.app_context():
        service_instance = factories.CDNDedicatedWAFServiceInstanceFactory.create(
            id="1234",
            domain_names=["example.com", "foo.com"],
            domain_internal="fake1234.cloudfront.net",
            route53_alias_hosted_zone="Z2FDTNDATAQYW2",
            cloudfront_distribution_id="FakeDistributionId",
            cloudfront_origin_hostname="origin_hostname",
            cloudfront_origin_path="origin_path",
            shield_associated_health_check={
                "domain_name": "example.com",
                "protection_id": protection_id,
                "health_check_id": "fake-health-check-id",
            },
            route53_health_checks=[
                {
                    "domain_name": "example.com",
                    "health_check_id": "fake-health-check-id",
                },
                {
                    "domain_name": "foo.com",
                    "health_check_id": "fake-health-check-id2",
                },
            ],
            dedicated_waf_web_acl_id="1234-dedicated-waf-id",
            dedicated_waf_web_acl_name="1234-dedicated-waf",
            dedicated_waf_web_acl_arn="1234-dedicated-waf-arn",
        )
        new_cert = factories.CertificateFactory.create(
            service_instance=service_instance,
            private_key_pem="NEWSOMEPRIVATEKEY",
            leaf_pem="NEWSOMECERTPEM",
            fullchain_pem="NEWFULLCHAINOFSOMECERTPEM",
            iam_server_certificate_id="new_certificate_id",
            iam_server_certificate_arn="new_certificate_arn",
            iam_server_certificate_name="new_certificate_name",
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
        no_context_clean_db.session.add(service_instance)
        no_context_clean_db.session.add(current_cert)
        no_context_clean_db.session.add(new_cert)
        no_context_clean_db.session.commit()
        no_context_clean_db.session.expunge_all()
        return service_instance


def test_waf_delete_web_acl_gives_up_after_max_retries(
    no_context_app, service_instance, wafv2
):
    with no_context_app.app_context():
        operation = factories.OperationFactory.create(service_instance=service_instance)

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
            waf._delete_web_acl_with_retries(operation.id, service_instance)


def test_waf_delete_web_acl_succeeds_on_retry(no_context_app, service_instance, wafv2):
    with no_context_app.app_context():
        operation = factories.OperationFactory.create(service_instance=service_instance)

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

        waf._delete_web_acl_with_retries(operation.id, service_instance)

        wafv2.assert_no_pending_responses()
