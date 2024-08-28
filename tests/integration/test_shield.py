import pytest
import uuid

from broker.tasks.shield import update_associated_health_checks
from broker.extensions import db
from broker.models import CDNDedicatedWAFServiceInstance

from tests.lib import factories


@pytest.fixture
def service_instance():
    service_instance = factories.CDNDedicatedWAFServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
        forwarded_headers=["HOST"],
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
    db.session.add(service_instance)
    db.session.add(current_cert)
    db.session.add(new_cert)
    db.session.commit()
    db.session.expunge_all()
    return service_instance


@pytest.fixture
def provision_operation(service_instance):
    operation = factories.OperationFactory.create(
        id=4321, service_instance=service_instance
    )
    return operation


def test_shield_update_no_change_associated_health_check(
    clean_db, service_instance, provision_operation, shield
):
    db.session.expunge_all()
    service_instance = db.session.get(CDNDedicatedWAFServiceInstance, "1234")
    # certificate = service_instance.new_certificate

    service_instance.domain_names = ["example.com", "bar.com"]
    db.session.add(service_instance)
    db.session.commit()
    db.session.expunge_all()

    protection_id = str(uuid.uuid4())
    protection = {
        "Id": protection_id,
        "ResourceArn": service_instance.cloudfront_distribution_arn,
    }
    shield.expect_list_protections([protection])

    update_associated_health_checks.call_local("4321")

    shield.assert_no_pending_responses()

    # db.session.expunge_all()
    # service_instance = db.session.get(CDNDedicatedWAFServiceInstance, "1234")
    # operation = db.session.get(Operation, "4321")
    # db.session.expunge_all()
