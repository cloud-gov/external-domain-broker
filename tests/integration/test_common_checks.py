from datetime import date, datetime
import time

import pytest

from broker.extensions import config
from broker.models import (
    ALBServiceInstance,
    MigrationServiceInstance,
    DedicatedALBServiceInstance,
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
)
from tests.lib.factories import ALBServiceInstanceFactory


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        DedicatedALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        MigrationServiceInstance,
    ],
)
def test_refuses_to_provision_synchronously(client, instance_model):
    client.provision_instance(instance_model, "4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        DedicatedALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        MigrationServiceInstance,
    ],
)
def test_refuses_to_provision_synchronously_by_default(client, instance_model):
    client.provision_instance(instance_model, "4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        DedicatedALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        MigrationServiceInstance,
    ],
)
def test_refuses_to_provision_without_domains(client, instance_model):
    client.provision_instance(instance_model, "4321")

    assert "domains" in client.response.body
    assert client.response.status_code == 400


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        DedicatedALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        MigrationServiceInstance,
    ],
)
def test_refuses_to_provision_with_duplicate_domains(client, dns, instance_model):
    ALBServiceInstanceFactory.create(domain_names=["foo.com", "bar.com"])
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.provision_instance(
        instance_model, "4321", params={"domains": "example.com, foo.com"}
    )

    assert "already exists" in client.response.body, client.response.body
    assert client.response.status_code == 400, client.response.body


@pytest.mark.parametrize(
    "instance_model,expected_status",
    [
        (ALBServiceInstance, 202),
        (DedicatedALBServiceInstance, 202),
        (CDNServiceInstance, 202),
        (MigrationServiceInstance, 201),
        (CDNDedicatedWAFServiceInstance, 202),
    ],
)
def test_doesnt_refuse_to_provision_with_duplicate_domains_when_not_configured_to(
    app, client, dns, instance_model, expected_status
):
    old_ignore = config.IGNORE_DUPLICATE_DOMAINS
    config.IGNORE_DUPLICATE_DOMAINS = True
    ALBServiceInstanceFactory.create(domain_names=["foo.com", "bar.com"])
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.provision_instance(
        instance_model, "4321", params={"domains": "example.com, foo.com"}
    )

    assert client.response.status_code == expected_status, client.response.body
    config.IGNORE_DUPLICATE_DOMAINS = old_ignore


@pytest.mark.parametrize(
    "instance_model,expected_status",
    [
        (ALBServiceInstance, 202),
        (DedicatedALBServiceInstance, 202),
        (CDNServiceInstance, 202),
        (MigrationServiceInstance, 201),
        (CDNDedicatedWAFServiceInstance, 202),
    ],
)
def test_duplicate_domain_check_ignores_deactivated(
    client, dns, instance_model, expected_status
):
    ALBServiceInstanceFactory.create(
        domain_names="foo.com", deactivated_at=datetime.utcnow()
    )
    dns.add_cname("_acme-challenge.foo.com")

    client.provision_instance(instance_model, "4321", params={"domains": "foo.com"})

    assert client.response.status_code == expected_status, client.response.body


@pytest.mark.parametrize(
    "instance_model",
    [
        ALBServiceInstance,
        DedicatedALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        MigrationServiceInstance,
    ],
)
def test_refuses_to_provision_without_any_acme_challenge_CNAMEs(client, instance_model):
    client.provision_instance(
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
        DedicatedALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        MigrationServiceInstance,
    ],
)
def test_refuses_to_provision_without_one_acme_challenge_CNAME(
    client, dns, instance_model
):
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_instance(
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
        DedicatedALBServiceInstance,
        CDNServiceInstance,
        CDNDedicatedWAFServiceInstance,
        MigrationServiceInstance,
    ],
)
def test_refuses_to_provision_with_incorrect_acme_challenge_CNAME(
    client, dns, instance_model
):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com", target="INCORRECT")
    client.provision_instance(
        instance_model, "4321", params={"domains": "bar.com,foo.com"}
    )

    desc = client.response.json.get("description")

    assert "is set incorrectly" in desc

    assert " _acme-challenge.foo.com " in desc
    assert " _acme-challenge.foo.com.domains.cloud.test" in desc
    assert " INCORRECT" in desc

    assert " _acme-challenge.bar.com" not in desc
    assert client.response.status_code == 400
