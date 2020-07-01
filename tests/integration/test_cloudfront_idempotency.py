import pytest

from broker.tasks.cloudfront import create_distribution
from broker.extensions import db
from broker.models import CDNServiceInstance

from tests.lib import factories


@pytest.fixture
def service_instance():
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com", "foo.com"],
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        private_key_pem="SOMEPRIVATEKEY",
        origin_protocol_policy="https-only",
        forwarded_headers=["HOST"],
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        service_instance=service_instance,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        service_instance=service_instance,
    )
    db.session.refresh(service_instance)
    return service_instance


@pytest.fixture
def provision_operation(service_instance):
    operation = factories.OperationFactory.create(
        id=4321, service_instance=service_instance
    )
    return operation


def test_create_distribution_existing_distribution(
    clean_db, service_instance, cloudfront, provision_operation
):
    cloudfront.expect_get_distribution(
        caller_reference="asdf",
        domains=service_instance.domain_names,
        certificate_id=service_instance.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
        status="InProcess",
    )
    create_distribution.call_local(provision_operation.id)


def test_create_distribution_referencing_nonexistent_distribution(
    clean_db, service_instance, cloudfront, provision_operation
):
    cloudfront.expect_get_distribution_returning_no_such_distribution(
        distribution_id=service_instance.cloudfront_distribution_id
    )
    cloudfront.expect_create_distribution(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=service_instance.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
    )

    create_distribution.call_local(provision_operation.id)

    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("1234")

    assert service_instance.cloudfront_distribution_arn
    assert service_instance.cloudfront_distribution_arn.startswith("arn:aws:cloudfront")
    assert service_instance.cloudfront_distribution_arn.endswith("FakeDistributionId")
    assert service_instance.cloudfront_distribution_id == "FakeDistributionId"
    assert service_instance.domain_internal == "fake1234.cloudfront.net"
