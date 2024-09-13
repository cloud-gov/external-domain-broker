from datetime import date

import pytest

from broker.tasks.iam import (
    upload_server_certificate,
    delete_server_certificate,
    delete_previous_server_certificate,
)
from broker.models import CDNServiceInstance, Operation, Certificate

from tests.lib import factories
from tests.lib.identifiers import get_server_certificate_name


@pytest.fixture
def service_instance(
    clean_db, service_instance_id, operation_id, current_cert_id, new_cert_id
):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id=service_instance_id,
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
        id=new_cert_id,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        id=current_cert_id,
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


@pytest.fixture
def alb_service_instance(
    clean_db, service_instance_id, operation_id, current_cert_id, new_cert_id
):
    service_instance = factories.ALBServiceInstanceFactory.create(
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
        iam_server_certificate_name=get_server_certificate_name(
            service_instance_id, new_cert_id
        ),
        id=new_cert_id,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name=get_server_certificate_name(
            service_instance_id, current_cert_id
        ),
        id=current_cert_id,
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


@pytest.fixture
def alb_service_instance_without_new_cert(clean_db, alb_service_instance):
    alb_service_instance.new_certificate = None
    clean_db.session.add(alb_service_instance)
    clean_db.session.commit()
    return alb_service_instance


def test_reupload_certificate_ok(
    clean_db,
    iam_commercial,
    service_instance,
    simple_regex,
    operation_id,
    service_instance_id,
):
    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(CDNServiceInstance, service_instance_id)
    certificate = service_instance.new_certificate
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam_commercial.expect_upload_server_certificate(
        name=get_server_certificate_name(service_instance_id, certificate.id),
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path="/cloudfront/external-domains-test/",
    )
    iam_commercial.expect_tag_server_certificate(
        get_server_certificate_name(service_instance_id, certificate.id),
        [],
    )

    upload_server_certificate.call_local(operation_id)

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(CDNServiceInstance, service_instance_id)
    certificate = service_instance.new_certificate
    operation = clean_db.session.get(Operation, operation_id)
    updated_at = operation.updated_at.timestamp()
    clean_db.session.expunge_all()
    # unstubbed, so an error should be raised if we do try
    upload_server_certificate.call_local(operation_id)
    operation = clean_db.session.get(Operation, operation_id)
    assert updated_at != operation.updated_at.timestamp()


def test_upload_certificate_already_exists(
    clean_db,
    iam_commercial,
    service_instance_id,
    simple_regex,
    operation_id,
    service_instance,
):
    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(CDNServiceInstance, service_instance_id)
    certificate = service_instance.new_certificate
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    server_certificate_name = get_server_certificate_name(
        service_instance_id, certificate.id
    )
    iam_commercial.expect_upload_server_certificate_raising_duplicate(
        name=server_certificate_name,
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path="/cloudfront/external-domains-test/",
    )
    iam_commercial.expect_get_server_certificate(
        name=server_certificate_name,
    )
    iam_commercial.expect_tag_server_certificate(
        server_certificate_name,
        [],
    )

    upload_server_certificate.call_local(operation_id)

    iam_commercial.assert_no_pending_responses()


def test_delete_server_certificate(
    clean_db,
    iam_govcloud,
    alb_service_instance,
    operation_id,
    current_cert_id,
    new_cert_id,
):
    iam_govcloud.expect_get_server_certificate(
        get_server_certificate_name(alb_service_instance.id, new_cert_id),
    )
    iam_govcloud.expects_delete_server_certificate(
        get_server_certificate_name(alb_service_instance.id, new_cert_id),
    )
    iam_govcloud.expect_get_server_certificate(
        get_server_certificate_name(alb_service_instance.id, current_cert_id),
    )
    iam_govcloud.expects_delete_server_certificate(
        get_server_certificate_name(alb_service_instance.id, current_cert_id),
    )

    delete_server_certificate.call_local(operation_id)

    iam_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()


def test_delete_server_certificate_current_cert_missing(
    clean_db,
    iam_govcloud,
    alb_service_instance,
    service_instance_id,
    operation_id,
    current_cert_id,
    new_cert_id,
):
    assert alb_service_instance.current_certificate is not None
    assert alb_service_instance.new_certificate is not None

    iam_govcloud.expect_get_server_certificate(
        get_server_certificate_name(service_instance_id, new_cert_id),
    )
    iam_govcloud.expects_delete_server_certificate(
        get_server_certificate_name(service_instance_id, new_cert_id),
    )
    iam_govcloud.expect_get_server_certificate_returning_no_such_entity(
        get_server_certificate_name(service_instance_id, current_cert_id),
    )

    delete_server_certificate.call_local(operation_id)

    iam_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()


def test_delete_server_certificate_new_cert_missing(
    clean_db,
    iam_govcloud,
    alb_service_instance,
    service_instance_id,
    operation_id,
    current_cert_id,
    new_cert_id,
):
    assert alb_service_instance.current_certificate is not None
    assert alb_service_instance.new_certificate is not None

    iam_govcloud.expect_get_server_certificate_returning_no_such_entity(
        get_server_certificate_name(service_instance_id, new_cert_id),
    )
    iam_govcloud.expect_get_server_certificate(
        get_server_certificate_name(service_instance_id, current_cert_id),
    )
    iam_govcloud.expects_delete_server_certificate(
        get_server_certificate_name(service_instance_id, current_cert_id),
    )

    delete_server_certificate.call_local(operation_id)

    iam_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()


def test_delete_previous_server_certificate_happy_path(
    clean_db,
    iam_govcloud,
    alb_service_instance_without_new_cert,
    operation_id,
    new_cert_id,
):
    certificate = clean_db.session.get(Certificate, new_cert_id)
    iam_govcloud.expect_get_server_certificate(
        get_server_certificate_name(
            alb_service_instance_without_new_cert.id, new_cert_id
        ),
    )
    iam_govcloud.expects_delete_server_certificate(
        get_server_certificate_name(
            alb_service_instance_without_new_cert.id, new_cert_id
        ),
    )

    delete_previous_server_certificate.call_local(operation_id)

    iam_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    certificate = clean_db.session.get(Certificate, new_cert_id)
    assert not certificate


def test_delete_previous_server_certificate_unexpected_error(
    iam_govcloud, alb_service_instance_without_new_cert, operation_id, new_cert_id
):
    iam_govcloud.expect_get_server_certificate(
        get_server_certificate_name(
            alb_service_instance_without_new_cert.id, new_cert_id
        ),
    )
    iam_govcloud.expects_delete_server_certificate_unexpected_error(
        get_server_certificate_name(
            alb_service_instance_without_new_cert.id, new_cert_id
        ),
    )

    with pytest.raises(Exception):
        delete_previous_server_certificate.call_local(operation_id)

    iam_govcloud.assert_no_pending_responses()


def test_delete_previous_server_certificate_already_deleted(
    clean_db,
    iam_govcloud,
    alb_service_instance_without_new_cert,
    operation_id,
    new_cert_id,
):
    iam_govcloud.expects_get_server_certificate_returning_no_such_entity(
        get_server_certificate_name(
            alb_service_instance_without_new_cert.id, new_cert_id
        ),
    )
    delete_previous_server_certificate.call_local(operation_id)

    iam_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    certificate = clean_db.session.get(Certificate, new_cert_id)
    assert not certificate


def test_delete_previous_server_certificate_error_on_get_server_certificate(
    iam_govcloud,
    alb_service_instance_without_new_cert,
    operation_id,
    new_cert_id,
):
    iam_govcloud.expects_get_server_certificate_unexpected_error(
        get_server_certificate_name(
            alb_service_instance_without_new_cert.id, new_cert_id
        ),
    )
    iam_govcloud.expects_delete_server_certificate_access_denied(
        get_server_certificate_name(
            alb_service_instance_without_new_cert.id, new_cert_id
        ),
    )

    with pytest.raises(Exception):
        delete_previous_server_certificate.call_local(operation_id)

    iam_govcloud.assert_no_pending_responses()
