import json

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


def test_provision_creates_provision_operation(client):
    client.provision_instance("4321", accepts_incomplete="true")

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


def test_provision_creates_LE_user(client, tasks, pebble):
    client.provision_instance("4321", accepts_incomplete="true")

    assert client.response.status_code == 202, client.response.body
    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)
    assert operation

    tasks.run_all_queued()

    acme_user = ServiceInstance.query.get("4321").acme_user
    assert acme_user
    assert "RSA" in acme_user.private_key
    assert "@gsa.gov" in acme_user.email
    assert "localhost:14000" in acme_user.uri
    registration = json.loads(acme_user.registration_json)
    assert "body" in registration
