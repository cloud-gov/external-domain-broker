import pytest
import uuid

from broker.lib.cdn import is_cdn_instance
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
def test_cdn_handle_domain_updates_no_change(
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

        (updated_domain_names, no_domain_updates) = handle_domain_updates(
            dict(domains=domain_names), instance
        )

        assert no_domain_updates == True
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
def test_cdn_handle_domain_updates_not_specified(
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

        (updated_domain_names, no_domain_updates) = handle_domain_updates(
            dict(), instance
        )

        assert no_domain_updates == True
        assert updated_domain_names == None


@pytest.mark.parametrize(
    "factory",
    [
        factories.ALBServiceInstanceFactory,
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
        factories.DedicatedALBServiceInstanceFactory,
    ],
)
def test_cdn_handle_domain_updates_with_changes(
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
        (updated_domain_names, no_domain_updates) = handle_domain_updates(
            dict(domains=domain_names), instance
        )

        assert no_domain_updates == False
        assert updated_domain_names == domain_names
