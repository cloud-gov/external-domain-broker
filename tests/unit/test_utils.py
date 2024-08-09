import pytest
import uuid

from openbrokerapi import errors

from broker.lib.utils import parse_domain_options, validate_domain_name_changes
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
def test_validate_domain_name_changes_no_change(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.foo.example.com")
        domain_names = ["foo.example.com"]

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

        updated_domain_names = validate_domain_name_changes(domain_names, instance)
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
def test_validate_domain_name_changes_not_specified(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.baz.example.com")
        domain_names = ["baz.example.com"]

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

        updated_domain_names = validate_domain_name_changes([], instance)
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
def test_validate_domain_name_changes_with_changes(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.bar.example.com")
        domain_names = ["bar.example.com"]

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

        dns.add_cname("_acme-challenge.moo.example.com")
        domain_names = ["moo.example.com"]

        updated_domain_names = validate_domain_name_changes(domain_names, instance)
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
def test_validate_domain_name_changes_errors_on_missing_dns(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.moo.example.com")
        domain_names = ["moo.example.com", "cow.example.net"]

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
            validate_domain_name_changes(domain_names, instance)


@pytest.mark.parametrize(
    "factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
    ],
)
def test_validate_domain_name_changes_errors_on_non_unique_domains(
    no_context_clean_db, no_context_app, dns, factory
):
    with no_context_app.app_context():
        dns.add_cname("_acme-challenge.moo.example.com")
        dns.add_cname("_acme-challenge.cow.example.net")

        existing_instance_domain_names = ["foo.example.com", "cow.example.net"]
        existing_instance = factory.create(
            id=str(uuid.uuid4()),
            domain_names=existing_instance_domain_names,
        )
        no_context_clean_db.session.add(existing_instance)
        no_context_clean_db.session.commit()

        domain_names = ["moo.example.com", "cow.example.net"]
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
            validate_domain_name_changes(domain_names, new_instance)
