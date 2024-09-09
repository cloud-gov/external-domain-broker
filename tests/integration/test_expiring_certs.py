import pytest
import random
from datetime import datetime, timedelta, timezone

from broker.tasks.cron import get_expiring_certs
from broker.models import Certificate

from tests.lib import factories


@pytest.fixture
def expires_at_needs_renewal():
    return datetime.now(timezone.utc) + timedelta(days=29)


@pytest.fixture
def service_instance(
    clean_db,
    operation_id,
    current_cert_id,
    new_cert_id,
    service_instance_id,
    expires_at_needs_renewal,
):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
    )
    new_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=new_cert_id,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        id=current_cert_id,
        expires_at=expires_at_needs_renewal,
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


def test_get_expiring_certs(
    service_instance, current_cert_id, expires_at_needs_renewal
):
    certificates = get_expiring_certs()
    assert len(certificates) == 1
    assert certificates[0].id == int(current_cert_id)
    assert certificates[0].expires_at == expires_at_needs_renewal


def test_get_expiring_certs_ignores_old_certs(
    clean_db, service_instance, current_cert_id
):
    old_cert_id = str(random.randrange(0, 10000))
    old_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        id=old_cert_id,
        expires_at=datetime.now() - timedelta(days=30),  # 30 days ago
    )
    clean_db.session.add(old_cert)
    clean_db.session.commit()
    clean_db.session.expunge_all()
    assert len(get_expiring_certs()) == 1


def test_get_expiring_certs_expires_in_future(
    clean_db, service_instance, current_cert_id
):
    current_certificate = clean_db.session.get(Certificate, current_cert_id)
    current_certificate.expires_at = datetime.now() + timedelta(days=31)
    clean_db.session.add(current_certificate)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    assert len(get_expiring_certs()) == 0


def test_get_expiring_certs_instance_deactivated(
    clean_db, service_instance, current_cert_id
):
    service_instance.deactivated_at = datetime.now()
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    assert len(get_expiring_certs()) == 0
