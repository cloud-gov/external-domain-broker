from datetime import date

import pytest

from broker.tasks.iam import upload_server_certificate
from broker.extensions import db
from broker.models import CDNServiceInstance, Operation

from tests.lib import factories


@pytest.fixture
def service_instance():
    service_instance = factories.CDNServiceInstanceFactory.create(
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


def test_reupload_certificate_ok(
    clean_db, iam_commercial, service_instance, provision_operation, simple_regex
):
    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "1234")
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
    iam_commercial.expect_tag_server_certificate(
        f"{service_instance.id}-{today}-{certificate.id}",
        [],
    )

    upload_server_certificate.call_local("4321")

    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "1234")
    certificate = service_instance.new_certificate
    operation = db.session.get(Operation, "4321")
    updated_at = operation.updated_at.timestamp()
    db.session.expunge_all()
    # unstubbed, so an error should be raised if we do try
    upload_server_certificate.call_local("4321")
    operation = db.session.get(Operation, "4321")
    assert updated_at != operation.updated_at.timestamp()


def test_upload_certificate_already_exists(
    clean_db, iam_commercial, service_instance, provision_operation, simple_regex
):
    db.session.expunge_all()
    service_instance = db.session.get(CDNServiceInstance, "1234")
    certificate = service_instance.new_certificate
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam_commercial.expect_upload_server_certificate_raising_duplicate(
        name=f"{service_instance.id}-{today}-{certificate.id}",
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path="/cloudfront/external-domains-test/",
    )
    iam_commercial.expect_get_server_certificate(
        name=f"{service_instance.id}-{today}-{certificate.id}",
        cert=certificate.leaf_pem,
        chain=certificate.fullchain_pem,
        path="/cloudfront/external-domains-test/",
    )
    iam_commercial.expect_tag_server_certificate(
        f"{service_instance.id}-{today}-{certificate.id}",
        [],
    )

    upload_server_certificate.call_local("4321")

    iam_commercial.assert_no_pending_responses()
