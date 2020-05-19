import json

from openbrokerapi.service_broker import OperationState

from broker.models import Operation, ServiceInstance
from broker import db


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
    assert "_acme-challenge.foo.com.domains.cloud.test" in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_provision_without_one_acme_challenge_CNAME(client, dns):
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com" not in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_provision_with_incorrect_acme_challenge_CNAME(client, dns):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com", target="INCORRECT")
    client.provision_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")

    assert "is set incorrectly" in desc

    assert " _acme-challenge.foo.com " in desc
    assert " _acme-challenge.foo.com.domains.cloud.test" in desc
    assert " INCORRECT" in desc

    assert " _acme-challenge.bar.com" not in desc
    assert client.response.status_code == 400


def test_provision_creates_provision_operation(client, dns):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_instance("4321", params={"domains": "example.com, Foo.com"})

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
    assert instance.domain_names == ["example.com", "foo.com"]


def test_provision_creates_LE_user(client, tasks, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        "4321", accepts_incomplete="true", params={"domains": "example.com"}
    )

    assert client.response.status_code == 202, client.response.body

    tasks.run_pipeline_stages(1)

    service_instance = ServiceInstance.query.get("4321")
    acme_user = service_instance.acme_user
    assert acme_user
    assert "RSA" in acme_user.private_key_pem
    assert "@gsa.gov" in acme_user.email
    assert "localhost:14000" in acme_user.uri
    assert "body" in json.loads(acme_user.registration_json)


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


def test_provision_initiates_LE_challenge(client, tasks, dns):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_instance(
        "4321", accepts_incomplete="true", params={"domains": "example.com,foo.com"}
    )

    assert client.response.status_code == 202, client.response.body

    tasks.run_pipeline_stages(3)

    service_instance = ServiceInstance.query.get("4321")

    assert service_instance.challenges.count() == 2


def test_provision_updates_TXT_record(client, tasks, dns, route53):
    dns.add_cname("_acme-challenge.example.com")
    route53.expect_create_txt_for("_acme-challenge.example.com.domains.cloud.test")

    client.provision_instance(
        "4321", accepts_incomplete="true", params={"domains": "example.com"}
    )

    assert client.response.status_code == 202, client.response.body

    tasks.run_pipeline_stages(4)


def test_provision_finishes_certificate_creation(client, tasks, dns, route53):
    dns.add_cname("_acme-challenge.example.com")
    route53.expect_create_txt_for("_acme-challenge.example.com.domains.cloud.test")

    client.provision_instance(
        "4321", accepts_incomplete="true", params={"domains": "example.com"}
    )
    assert client.response.status_code == 202, client.response.body

    tasks.run_pipeline_stages(4)

    service_instance = ServiceInstance.query.get("4321")
    challenge = service_instance.challenges.first()
    assert challenge.validation_contents is not None

    dns.add_txt(
        "_acme-challenge.example.com.domains.cloud.test.",
        f"{challenge.validation_contents}",
    )

    tasks.run_pipeline_stages(1)

    db.session.refresh(service_instance)

    assert "BEGIN CERTIFICATE" in service_instance.fullchain_pem
