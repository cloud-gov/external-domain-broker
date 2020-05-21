import pytest
from openbrokerapi.service_broker import OperationState

from broker.models import Operation, ServiceInstance
from tests import factories


@pytest.fixture
def service_instance():
    return factories.ServiceInstanceFactory.create(id="1234")


def test_refuses_to_deprovision_synchronously(client, service_instance):
    client.deprovision_instance(service_instance.id, accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_deprovision_synchronously_by_default(client, service_instance):
    client.deprovision_instance(service_instance.id, accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_deprovision_creates_deprovision_operation(client, service_instance):
    client.deprovision_instance(service_instance.id, accepts_incomplete="true")

    assert "AsyncRequired" not in client.response.body
    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == OperationState.IN_PROGRESS
    assert operation.service_instance_id == service_instance.id

    instance = ServiceInstance.query.get(operation.service_instance_id)
    assert instance is not None
