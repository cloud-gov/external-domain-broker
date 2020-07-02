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
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        private_key_pem="SOMEPRIVATEKEY",
        cert_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
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


@pytest.mark.focus
def test_reupload_certificate_ok(
    clean_db, iam_commercial, service_instance, provision_operation, simple_regex
):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("1234")
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam_commercial.expect_upload_server_certificate(
        name=f"{service_instance.id}-{today}",
        cert=service_instance.cert_pem,
        private_key=service_instance.private_key_pem,
        chain=service_instance.fullchain_pem,
        path="/cloudfront/external-domains-test/",
    )

    upload_server_certificate.call_local("4321")

    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("1234")
    iam_commercial.expect_upload_server_certificate_raising_duplicate(
        name=f"{service_instance.id}-{today}",
        cert=service_instance.cert_pem,
        private_key=service_instance.private_key_pem,
        chain=service_instance.fullchain_pem,
        path="/cloudfront/external-domains-test/",
    )
    upload_server_certificate.call_local("4321")
