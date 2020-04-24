from openbrokerapi.service_broker import OperationState

from broker.models import Operation, ServiceInstance
from tests import factories


def test_refuses_to_deprovision_synchronously(client):
    client.deprovision_instance(id="1234", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_deprovision_synchronously_by_default(client):
    client.deprovision_instance(id="1234", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_starts_instance_deprovisioning(client):
    factories.ServiceInstanceFactory.create(id="1234")

    client.deprovision_instance(id="1234")

    assert "AsyncRequired" not in client.response.body
    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == OperationState.IN_PROGRESS
    assert operation.service_instance_id == "1234"

    client.get_last_operation()

    assert "state" in client.response.json
    assert client.response.json["state"] == "in progress"
