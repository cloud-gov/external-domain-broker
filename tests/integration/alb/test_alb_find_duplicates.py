import pytest  # noqa F401

from tests.lib.factories import (
    CertificateFactory,
    ALBServiceInstanceFactory,
)

from broker.tasks.huey import huey

from broker.tasks.alb import find_duplicate_alb_certs

def test_no_duplicate_alb_certs(no_context_clean_db, no_context_app):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    CertificateFactory.create(
      service_instance=service_instance,
    )

    no_context_clean_db.session.commit()

    results = find_duplicate_alb_certs()

    assert len(results) == 0

def test_non_current_duplicate_alb_cert(no_context_clean_db, no_context_app):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate = CertificateFactory.create(
      service_instance=service_instance,
    )
    CertificateFactory.create(
      service_instance=service_instance,
    )
    service_instance.current_certificate_id = certificate.id

    no_context_clean_db.session.commit()

    results = find_duplicate_alb_certs()

    assert len(results) == 1
    assert results == [("1234", 1)]

def test_multiple_non_current_duplicate_alb_certs(no_context_clean_db, no_context_app):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate = CertificateFactory.create(
        service_instance=service_instance,
    )
    CertificateFactory.create(
        service_instance=service_instance,
    )
    CertificateFactory.create(
        service_instance=service_instance,
    )
    service_instance.current_certificate_id = certificate.id

    no_context_clean_db.session.commit()

    results = find_duplicate_alb_certs()

    assert len(results) == 1
    assert results == [("1234", 2)]
