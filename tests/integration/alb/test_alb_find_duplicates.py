import pytest  # noqa F401

from tests.lib.factories import (
    CertificateFactory,
    ALBServiceInstanceFactory,
)

from broker.tasks.huey import huey

from broker.tasks.alb import find_duplicate_alb_certs

def test_find_duplicate_alb_certs(no_context_clean_db, no_context_app):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    CertificateFactory.create(
        service_instance=service_instance,
    )

    service_instance2 = ALBServiceInstanceFactory.create(id="5678")
    CertificateFactory.create(
        service_instance=service_instance2,
    )
    CertificateFactory.create(
        service_instance=service_instance2,
    )

    no_context_clean_db.session.commit()

    results = find_duplicate_alb_certs()

    assert len(results) == 1
    assert results == [("5678", 2)]
