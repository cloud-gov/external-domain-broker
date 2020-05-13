import json
import pytest

from openbrokerapi.service_broker import OperationState

from broker.models import Operation, ServiceInstance


def test_refuses_to_provision_synchronously(client):
    client.provision_instance("4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_synchronously_by_default(client):
    client.provision_instance("4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_without_domains(client):
    client.provision_instance("4321")

    assert "domains" in client.response.body
    assert client.response.status_code == 400


def test_refuses_to_provision_without_any_acme_challenge_CNAMEs(client):
    client.provision_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com " in desc
    assert "_acme-challenge.foo.com.domains.cloud.gov" in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.gov" in desc
    assert client.response.status_code == 400


def test_refuses_to_provision_without_one_acme_challenge_CNAME(client, dns):
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com" not in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.gov" in desc
    assert client.response.status_code == 400


def test_provision_creates_provision_operation(client, simple_regex, dns):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.cloud.gov")
    client.provision_instance("4321", params={"domains": "example.com, Cloud.Gov"})

    assert "AsyncRequired" not in client.response.body
    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == OperationState.IN_PROGRESS
    assert operation.service_instance_id == "4321"

    instance = ServiceInstance.query.get(operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["example.com", "cloud.gov"]

    client.get_last_operation("4321", operation_id)
    assert client.response.json.get("description") == simple_regex(
        r"run this command again"
    )


def test_provision_creates_LE_user(client, tasks, simple_regex, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        "4321", accepts_incomplete="true", params={"domains": "example.com"}
    )

    assert client.response.status_code == 202, client.response.body
    operation_id = client.response.json["operation"]

    tasks.run_pipeline_stages(1)

    service_instance = ServiceInstance.query.get("4321")
    acme_user = service_instance.acme_user
    assert acme_user
    assert "RSA" in acme_user.private_key_pem
    assert "@gsa.gov" in acme_user.email
    assert "localhost:14000" in acme_user.uri

    assert "body" in json.loads(acme_user.registration_json)

    client.get_last_operation("4321", operation_id)
    assert client.response.json.get("description") == simple_regex(
        r"run this command again"
    )


def test_provision_creates_private_key_and_csr(client, tasks, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        "4321", accepts_incomplete="true", params={"domains": "example.com"}
    )

    assert client.response.status_code == 202, client.response.body

    tasks.run_pipeline_stages(2)

    service_instance = ServiceInstance.query.get("4321")
    assert "BEGIN PRIVATE KEY" in service_instance.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in service_instance.csr_pem


def test_provision_initiates_LE_challenge(client, tasks, simple_regex, dns):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.cloud.gov")
    client.provision_instance(
        "4321", accepts_incomplete="true", params={"domains": "example.com,cloud.gov"}
    )

    assert client.response.status_code == 202, client.response.body
    operation_id = client.response.json["operation"]

    tasks.run_pipeline_stages(3)

    service_instance = ServiceInstance.query.get("4321")

    assert service_instance.challenges.count() == 2

    client.get_last_operation("4321", operation_id)
    description = client.response.json.get("description")
    assert description == simple_regex(r"add the following TXT DNS records:")

    for challenge in service_instance.challenges:
        assert challenge.validation_domain
        assert challenge.validation_contents
        assert "_acme-challenge." in challenge.validation_domain
        assert len(challenge.validation_contents) == 43
        assert description == simple_regex(rf"{challenge.validation_domain}")
        assert description == simple_regex(rf"{challenge.validation_contents}")
