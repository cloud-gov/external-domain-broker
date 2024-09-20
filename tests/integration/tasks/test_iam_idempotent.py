from datetime import date

import pytest

from broker.lib.cdn import is_cdn_instance
from broker.tasks.iam import (
    upload_server_certificate,
    delete_server_certificate,
    delete_previous_server_certificate,
)
from broker.models import (
    ALBServiceInstance,
    CDNServiceInstance,
    DedicatedALBServiceInstance,
    CDNDedicatedWAFServiceInstance,
    Operation,
    Certificate,
)

from tests.lib import factories
from tests.lib.identifiers import get_server_certificate_name


@pytest.fixture
def service_instance(
    clean_db,
    instance_factory,
    service_instance_id,
    operation_id,
    current_cert_id,
    new_cert_id,
):
    service_instance = instance_factory.create(
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
        iam_server_certificate_name=get_server_certificate_name(
            service_instance_id, new_cert_id
        ),
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        id=current_cert_id,
        iam_server_certificate_name=get_server_certificate_name(
            service_instance_id, current_cert_id
        ),
    )
    service_instance.current_certificate = current_cert
    service_instance.new_certificate = new_cert
    clean_db.session.add(service_instance)
    clean_db.session.add(current_cert)
    clean_db.session.add(new_cert)
    clean_db.session.commit()
    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )
    return service_instance


@pytest.fixture
def service_instance_without_new_cert(clean_db, service_instance):
    service_instance.new_certificate = None
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    return service_instance


@pytest.fixture
def iam(iam_commercial, iam_govcloud, service_instance):
    if is_cdn_instance(service_instance):
        iam = iam_commercial
    else:
        iam = iam_govcloud
    return iam


@pytest.fixture
def iam_certificate_path(service_instance):
    if is_cdn_instance(service_instance):
        path = "/cloudfront/external-domains-test/"
    else:
        path = "/alb/external-domains-test/"
    return path


@pytest.mark.parametrize(
    "instance_factory, instance_model",
    [
        [factories.ALBServiceInstanceFactory, ALBServiceInstance],
        [factories.CDNServiceInstanceFactory, CDNServiceInstance],
        [factories.DedicatedALBServiceInstanceFactory, DedicatedALBServiceInstance],
        [
            factories.CDNDedicatedWAFServiceInstanceFactory,
            CDNDedicatedWAFServiceInstance,
        ],
    ],
)
def test_reupload_certificate_ok(
    clean_db,
    instance_model,
    iam,
    iam_certificate_path,
    service_instance,
    simple_regex,
    operation_id,
    service_instance_id,
):
    certificate = service_instance.new_certificate
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam.expect_upload_server_certificate(
        name=get_server_certificate_name(service_instance_id, certificate.id),
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path=iam_certificate_path,
    )
    iam.expect_tag_server_certificate(
        get_server_certificate_name(service_instance_id, certificate.id),
        [],
    )

    upload_server_certificate.call_local(operation_id)

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(instance_model, service_instance_id)
    certificate = service_instance.new_certificate
    operation = clean_db.session.get(Operation, operation_id)
    updated_at = operation.updated_at.timestamp()

    # unstubbed, so an error should be raised if we do try
    clean_db.session.expunge_all()
    upload_server_certificate.call_local(operation_id)
    operation = clean_db.session.get(Operation, operation_id)
    assert updated_at != operation.updated_at.timestamp()


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_upload_certificate_already_exists(
    iam,
    iam_certificate_path,
    service_instance_id,
    simple_regex,
    operation_id,
    service_instance,
):
    certificate = service_instance.new_certificate
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    server_certificate_name = get_server_certificate_name(
        service_instance_id, certificate.id
    )
    iam.expect_upload_server_certificate_raising_duplicate(
        name=server_certificate_name,
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path=iam_certificate_path,
    )
    iam.expect_get_server_certificate(
        name=server_certificate_name,
    )
    iam.expect_tag_server_certificate(
        server_certificate_name,
        [],
    )

    upload_server_certificate.call_local(operation_id)

    iam.assert_no_pending_responses()


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_delete_server_certificate(
    clean_db,
    iam,
    service_instance,
    operation_id,
    current_cert_id,
    new_cert_id,
):
    iam.expect_get_server_certificate(
        get_server_certificate_name(service_instance.id, new_cert_id),
    )
    iam.expects_delete_server_certificate(
        get_server_certificate_name(service_instance.id, new_cert_id),
    )
    iam.expect_get_server_certificate(
        get_server_certificate_name(service_instance.id, current_cert_id),
    )
    iam.expects_delete_server_certificate(
        get_server_certificate_name(service_instance.id, current_cert_id),
    )

    delete_server_certificate.call_local(operation_id)

    iam.assert_no_pending_responses()

    clean_db.session.expunge_all()


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_delete_server_certificate_current_cert_missing(
    clean_db,
    iam,
    service_instance,
    operation_id,
    current_cert_id,
    new_cert_id,
):
    assert service_instance.current_certificate is not None
    assert service_instance.new_certificate is not None

    iam.expect_get_server_certificate(
        get_server_certificate_name(service_instance.id, new_cert_id),
    )
    iam.expects_delete_server_certificate(
        get_server_certificate_name(service_instance.id, new_cert_id),
    )
    iam.expect_get_server_certificate_returning_no_such_entity(
        get_server_certificate_name(service_instance.id, current_cert_id),
    )

    delete_server_certificate.call_local(operation_id)

    iam.assert_no_pending_responses()

    clean_db.session.expunge_all()


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_delete_server_certificate_new_cert_missing(
    clean_db,
    iam,
    service_instance,
    operation_id,
    current_cert_id,
    new_cert_id,
):
    assert service_instance.current_certificate is not None
    assert service_instance.new_certificate is not None

    iam.expect_get_server_certificate_returning_no_such_entity(
        get_server_certificate_name(service_instance.id, new_cert_id),
    )
    iam.expect_get_server_certificate(
        get_server_certificate_name(service_instance.id, current_cert_id),
    )
    iam.expects_delete_server_certificate(
        get_server_certificate_name(service_instance.id, current_cert_id),
    )

    delete_server_certificate.call_local(operation_id)

    iam.assert_no_pending_responses()

    clean_db.session.expunge_all()


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_delete_previous_server_certificate_happy_path(
    clean_db,
    iam,
    service_instance_without_new_cert,
    operation_id,
    new_cert_id,
):
    certificate = clean_db.session.get(Certificate, new_cert_id)
    iam.expect_get_server_certificate(
        get_server_certificate_name(service_instance_without_new_cert.id, new_cert_id),
    )
    iam.expects_delete_server_certificate(
        get_server_certificate_name(service_instance_without_new_cert.id, new_cert_id),
    )

    delete_previous_server_certificate.call_local(operation_id)

    iam.assert_no_pending_responses()

    clean_db.session.expunge_all()

    certificate = clean_db.session.get(Certificate, new_cert_id)
    assert not certificate


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_delete_previous_server_certificate_unexpected_error(
    iam, service_instance_without_new_cert, operation_id, new_cert_id
):
    iam.expect_get_server_certificate(
        get_server_certificate_name(service_instance_without_new_cert.id, new_cert_id),
    )
    iam.expects_delete_server_certificate_unexpected_error(
        get_server_certificate_name(service_instance_without_new_cert.id, new_cert_id),
    )

    with pytest.raises(Exception):
        delete_previous_server_certificate.call_local(operation_id)

    iam.assert_no_pending_responses()


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_delete_previous_server_certificate_already_deleted(
    clean_db,
    iam,
    service_instance_without_new_cert,
    operation_id,
    new_cert_id,
):
    iam.expects_get_server_certificate_returning_no_such_entity(
        get_server_certificate_name(service_instance_without_new_cert.id, new_cert_id),
    )
    delete_previous_server_certificate.call_local(operation_id)

    iam.assert_no_pending_responses()

    clean_db.session.expunge_all()

    certificate = clean_db.session.get(Certificate, new_cert_id)
    assert not certificate


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_delete_previous_server_certificate_error_on_get_server_certificate(
    iam,
    service_instance_without_new_cert,
    operation_id,
    new_cert_id,
):
    iam.expects_get_server_certificate_unexpected_error(
        get_server_certificate_name(service_instance_without_new_cert.id, new_cert_id),
    )
    iam.expects_delete_server_certificate_access_denied(
        get_server_certificate_name(service_instance_without_new_cert.id, new_cert_id),
    )

    with pytest.raises(Exception):
        delete_previous_server_certificate.call_local(operation_id)

    iam.assert_no_pending_responses()
