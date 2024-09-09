import pytest
import uuid

from tests.lib.factories import (
    ALBServiceInstanceFactory,
    CertificateFactory,
    OperationFactory,
)

from broker.models import ALBServiceInstance
from broker.tasks.alb import remove_certificate_from_previous_alb


@pytest.fixture
def previous_alb_listener_arn():
    return str(uuid.uuid4())


@pytest.fixture
def previous_certificate_arn(previous_alb_listener_arn):
    return f"{previous_alb_listener_arn}/certificate-arn-0"


@pytest.fixture
def service_instance(
    clean_db,
    current_cert_id,
    service_instance_id,
    previous_certificate_arn,
    previous_alb_listener_arn,
    operation_id,
):
    """
    create a cdn service instance that needs renewal.
    This includes walking it through the first few ACME steps to create a user so we can reuse that user.
    """
    service_instance = ALBServiceInstanceFactory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloud.test",
        route53_alias_hosted_zone="ALBHOSTEDZONEID",
        previous_alb_listener_arn=previous_alb_listener_arn,
    )
    previous_cert = CertificateFactory.create(
        id=current_cert_id,
        service_instance=service_instance,
        iam_server_certificate_arn=previous_certificate_arn,
        private_key_pem="SOMEPRIVATEKEY",
    )

    clean_db.session.add(service_instance)
    clean_db.session.add(previous_cert)
    clean_db.session.commit()
    clean_db.session.expunge_all()
    OperationFactory.create(id=operation_id, service_instance=service_instance)
    return service_instance


def test_remove_certificate_from_previous_alb(
    service_instance,
    operation_id,
    previous_alb_listener_arn,
    previous_certificate_arn,
    alb,
):
    alb.expect_remove_certificate_from_listener(
        previous_alb_listener_arn,
        previous_certificate_arn,
    )
    alb.expect_get_certificates_for_listener(previous_alb_listener_arn, 0)

    remove_certificate_from_previous_alb.call_local(operation_id)

    alb.assert_no_pending_responses()


def test_remove_certificate_from_previous_alb_with_retries(
    service_instance,
    operation_id,
    previous_alb_listener_arn,
    previous_certificate_arn,
    alb,
):
    alb.expect_remove_certificate_from_listener(
        previous_alb_listener_arn,
        previous_certificate_arn,
    )
    alb.expect_get_certificates_for_listener(previous_alb_listener_arn, 1)
    alb.expect_get_certificates_for_listener(previous_alb_listener_arn, 1)
    alb.expect_get_certificates_for_listener(previous_alb_listener_arn, 0)

    remove_certificate_from_previous_alb.call_local(operation_id)

    alb.assert_no_pending_responses()


def test_remove_certificate_from_previous_alb_gives_up_after_max_retries(
    service_instance,
    operation_id,
    previous_alb_listener_arn,
    previous_certificate_arn,
    alb,
):
    alb.expect_remove_certificate_from_listener(
        previous_alb_listener_arn,
        previous_certificate_arn,
    )
    for _ in range(10):
        alb.expect_get_certificates_for_listener(previous_alb_listener_arn, 1)

    with pytest.raises(RuntimeError):
        remove_certificate_from_previous_alb.call_local(operation_id)

    alb.assert_no_pending_responses()
