import pytest  # noqa F401

# from huey.exceptions import CancelExecution

# from broker.extensions import config, db

from broker.models import Operation
from tests.lib.client import (
    # app,
    # clean_db,
    # client,
    # no_context_clean_db,
    no_context_app,
)  # noqa 401
from tests.lib.factories import (
    OperationFactory,
    CertificateFactory,
    ALBServiceInstanceFactory,
)

from broker.tasks.huey import huey

from broker.tasks.alb import scan_for_duplicate_alb_certs

@pytest.mark.focus
def test_scan_for_duplicate_alb_certs(no_context_clean_db, no_context_app):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate1 = CertificateFactory.create(
        service_instance=service_instance,
    )
    certificate2 = CertificateFactory.create(
        service_instance=service_instance,
    )
    no_context_clean_db.session.commit()

    results = scan_for_duplicate_alb_certs()

    assert len(results) == 1
