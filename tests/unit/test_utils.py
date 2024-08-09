import pytest
import uuid

from openbrokerapi import errors

from broker.lib.utils import parse_domain_options, handle_domain_updates
from tests.lib import factories


def test_parse_domains():
    assert parse_domain_options(dict(domains="example.com")) == ["example.com"]
    assert parse_domain_options(dict(domains="example.com,example.gov")) == [
        "example.com",
        "example.gov",
    ]
    assert parse_domain_options(dict(domains=["example.com"])) == ["example.com"]
    assert parse_domain_options(dict(domains=["example.com", "example.gov"])) == [
        "example.com",
        "example.gov",
    ]
    assert parse_domain_options(dict(domains=["eXaMpLe.cOm   "])) == ["example.com"]


@pytest.mark.parametrize(
    "factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
    ],
)
def test_handle_domain_updates_no_change(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.foo.com")
        domain_names = ["foo.com"]

        instance_id = str(uuid.uuid4())
        instance = factory.create(
            id=instance_id,
            domain_names=domain_names,
        )
        current_cert = factories.CertificateFactory.create(
            service_instance=instance,
            private_key_pem="SOMEPRIVATEKEY",
            iam_server_certificate_id="certificate_id",
            id=1000,
        )
        instance.current_certificate = current_cert
        no_context_clean_db.session.add(instance)
        no_context_clean_db.session.add(current_cert)
        no_context_clean_db.session.commit()

        assert instance.domain_names == domain_names
        assert instance.current_certificate == current_cert
        assert instance.current_certificate_id == 1000

        updated_domain_names = handle_domain_updates(
            dict(domains=domain_names), instance
        )
        assert updated_domain_names == []


@pytest.mark.parametrize(
    "factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
    ],
)
def test_handle_domain_updates_not_specified(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.baz.com")
        domain_names = ["baz.com"]

        instance_id = str(uuid.uuid4())
        instance = factory.create(
            id=instance_id,
            domain_names=domain_names,
        )
        current_cert = factories.CertificateFactory.create(
            service_instance=instance,
            private_key_pem="SOMEPRIVATEKEY",
            iam_server_certificate_id="certificate_id",
            id=1000,
        )
        instance.current_certificate = current_cert
        no_context_clean_db.session.add(instance)
        no_context_clean_db.session.add(current_cert)
        no_context_clean_db.session.commit()

        assert instance.domain_names == domain_names
        assert instance.current_certificate == current_cert
        assert instance.current_certificate_id == 1000

        updated_domain_names = handle_domain_updates(dict(), instance)
        assert updated_domain_names == []


@pytest.mark.parametrize(
    "factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
    ],
)
def test_handle_domain_updates_with_changes(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.bar.com")
        domain_names = ["bar.com"]

        instance_id = str(uuid.uuid4())
        instance = factory.create(
            id=instance_id,
            domain_names=domain_names,
        )
        current_cert = factories.CertificateFactory.create(
            service_instance=instance,
            private_key_pem="SOMEPRIVATEKEY",
            iam_server_certificate_id="certificate_id",
            id=1000,
        )
        instance.current_certificate = current_cert
        no_context_clean_db.session.add(instance)
        no_context_clean_db.session.add(current_cert)
        no_context_clean_db.session.commit()

        assert instance.domain_names == domain_names
        assert instance.current_certificate == current_cert
        assert instance.current_certificate_id == 1000

        dns.add_cname("_acme-challenge.moo.com")
        domain_names = ["moo.com"]

        updated_domain_names = handle_domain_updates(
            dict(domains=domain_names), instance
        )
        assert updated_domain_names == domain_names


@pytest.mark.parametrize(
    "factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
    ],
)
def test_handle_domain_errors_on_missing_dns(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.moo.com")
        domain_names = ["moo.com", "cow.com"]

        instance_id = str(uuid.uuid4())
        instance = factory.create(
            id=instance_id,
            domain_names=domain_names,
        )
        current_cert = factories.CertificateFactory.create(
            service_instance=instance,
            private_key_pem="SOMEPRIVATEKEY",
            iam_server_certificate_id="certificate_id",
            id=1000,
        )
        instance.current_certificate = current_cert
        no_context_clean_db.session.add(instance)
        no_context_clean_db.session.add(current_cert)
        no_context_clean_db.session.commit()

        assert instance.domain_names == domain_names
        assert instance.current_certificate == current_cert
        assert instance.current_certificate_id == 1000

        with pytest.raises(errors.ErrBadRequest):
            handle_domain_updates(dict(domains=domain_names), instance)


@pytest.mark.parametrize(
    "factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
    ],
)
def test_handle_domain_errors_on_non_unique_domains(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.moo.com")
        dns.add_cname("_acme-challenge.cow.com")

        existing_instance_domain_names = ["foo.com", "cow.com"]
        existing_instance = factory.create(
            id=str(uuid.uuid4()),
            domain_names=existing_instance_domain_names,
        )
        no_context_clean_db.session.add(existing_instance)
        no_context_clean_db.session.commit()

        domain_names = ["moo.com", "cow.com"]
        new_instance = factory.create(
            id=str(uuid.uuid4()),
            domain_names=domain_names,
        )
        current_cert = factories.CertificateFactory.create(
            service_instance=new_instance,
            private_key_pem="SOMEPRIVATEKEY",
            iam_server_certificate_id="certificate_id",
            id=1000,
        )
        new_instance.current_certificate = current_cert
        no_context_clean_db.session.add(new_instance)
        no_context_clean_db.session.add(current_cert)
        no_context_clean_db.session.commit()

        assert new_instance.domain_names == domain_names
        assert new_instance.current_certificate == current_cert
        assert new_instance.current_certificate_id == 1000

        with pytest.raises(errors.ErrBadRequest):
            handle_domain_updates(dict(domains=domain_names), new_instance)
