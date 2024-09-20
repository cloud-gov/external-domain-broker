from datetime import datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    ALBServiceInstance,
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
    DedicatedALBServiceInstance,
)

from tests.lib import factories


@pytest.fixture()
def service_instance_factory(instance_model):
    if instance_model == ALBServiceInstance:
        return factories.ALBServiceInstanceFactory
    elif instance_model == CDNDedicatedWAFServiceInstance:
        return factories.CDNDedicatedWAFServiceInstanceFactory
    elif instance_model == CDNServiceInstance:
        return factories.CDNServiceInstanceFactory
    elif instance_model == DedicatedALBServiceInstance:
        return factories.DedicatedALBServiceInstanceFactory


def alb_service_instance(service_instance_factory):
    service_instance = service_instance_factory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        alb_arn="alb-arn-1",
        alb_listener_arn="alb-listener-arn-1",
        domain_internal="fake1234.cloud.test",
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_arn="certificate_arn",
        iam_server_certificate_name="certificate_name",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1001,
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=1001,
        answered=True,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=1001,
        answered=True,
    )
    service_instance.current_certificate = current_cert
    db.session.add(service_instance)
    db.session.add(current_cert)
    db.session.commit()
    db.session.expunge_all()
    return service_instance


def cdn_service_instance(service_instance_factory):
    kwargs = {}
    if service_instance_factory == factories.CDNDedicatedWAFServiceInstanceFactory:
        kwargs["alarm_notification_email"] = "fake@localhost"
    service_instance = service_instance_factory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
        **kwargs,
    )
    new_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1002,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_arn="certificate_arn",
        iam_server_certificate_name="certificate_name",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1001,
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=1001,
        answered=True,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=1001,
        answered=True,
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=1002,
        answered=False,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=1002,
        answered=False,
    )
    service_instance.current_certificate = current_cert
    service_instance.new_certificate = new_cert
    db.session.add(service_instance)
    db.session.add(current_cert)
    db.session.add(new_cert)
    db.session.commit()
    db.session.expunge_all()
    return service_instance


@pytest.fixture
def service_instance(instance_model, service_instance_factory):
    if instance_model == ALBServiceInstance:
        return alb_service_instance(service_instance_factory)
    elif instance_model == CDNDedicatedWAFServiceInstance:
        return cdn_service_instance(service_instance_factory)
    elif instance_model == CDNServiceInstance:
        return cdn_service_instance(service_instance_factory)
    elif instance_model == DedicatedALBServiceInstance:
        return alb_service_instance(service_instance_factory)


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_refuses_to_update_synchronously(instance_model, client):
    client.update_instance(instance_model, "4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_refuses_to_update_synchronously_by_default(instance_model, client):
    client.update_instance(instance_model, "4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_refuses_to_update_with_duplicate_domains(
    instance_model, client, dns, service_instance_factory, service_instance
):
    service_instance_factory.create(domain_names=["foo.com", "bar.com"])
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.update_instance(
        instance_model, "4321", params={"domains": "example.com, foo.com"}
    )

    assert "already exists" in client.response.body, client.response.body
    assert client.response.status_code == 400, client.response.body


@pytest.mark.parametrize(
    "instance_model, expected_status_code",
    [
        (ALBServiceInstance, 200),
        (CDNServiceInstance, 202),
        (CDNDedicatedWAFServiceInstance, 202),
        (DedicatedALBServiceInstance, 200),
    ],
)
def test_duplicate_domain_check_ignores_self(
    instance_model, expected_status_code, client, dns, service_instance
):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.update_instance(
        instance_model,
        "4321",
        params={"domains": "example.com, foo.com"},
    )

    assert client.response.status_code == expected_status_code, client.response.body


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_update_duplicate_domain_check_ignores_deactivated(
    instance_model, client, dns, service_instance
):
    factories.CDNServiceInstanceFactory.create(
        domain_names="foo.com", deactivated_at=datetime.utcnow()
    )
    dns.add_cname("_acme-challenge.foo.com")

    client.update_instance(instance_model, "4321", params={"domains": "foo.com"})

    assert client.response.status_code == 202, client.response.body


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_refuses_to_update_without_any_acme_challenge_CNAMEs(
    instance_model, client, service_instance
):
    client.update_instance(
        instance_model, "4321", params={"domains": "bar.com,foo.com"}
    )

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com " in desc
    assert "_acme-challenge.foo.com.domains.cloud.test" in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_refuses_to_update_without_one_acme_challenge_CNAME(
    instance_model, client, dns, service_instance
):
    dns.add_cname("_acme-challenge.foo.com")
    client.update_instance(
        instance_model, "4321", params={"domains": "bar.com,foo.com"}
    )

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com" not in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_refuses_to_update_with_incorrect_acme_challenge_CNAME(
    instance_model, client, dns, service_instance
):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com", target="INCORRECT")
    client.update_instance(
        instance_model, "4321", params={"domains": "bar.com,foo.com"}
    )

    desc = client.response.json.get("description")

    assert "is set incorrectly" in desc

    assert " _acme-challenge.foo.com " in desc
    assert " _acme-challenge.foo.com.domains.cloud.test" in desc
    assert " INCORRECT" in desc

    assert " _acme-challenge.bar.com" not in desc
    assert client.response.status_code == 400


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_refuses_update_for_canceled_instance(
    instance_model, client, dns, service_instance
):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    service_instance.deactivated_at = datetime.now()
    db.session.add(service_instance)
    db.session.commit()

    client.update_instance(
        instance_model, "4321", params={"domains": "bar.com,foo.com"}
    )

    desc = client.response.json.get("description")
    assert "canceled" in desc
    assert client.response.status_code == 400


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_refuses_update_for_nonexistent_instance(instance_model, client, dns):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.update_instance(
        instance_model, "4321", params={"domains": "bar.com,foo.com"}
    )
    desc = client.response.json.get("description")
    assert "does not exist" in desc
    assert client.response.status_code == 400


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        DedicatedALBServiceInstance,
    ],
)
def test_refuses_update_for_instance_with_operation(
    instance_model, client, dns, service_instance
):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    factories.OperationFactory.create(service_instance=service_instance)
    client.update_instance(
        instance_model, "4321", params={"domains": "bar.com,foo.com"}
    )

    desc = client.response.json.get("description")

    assert "in progress" in desc
    assert client.response.status_code == 400
