from pprint import pp

from openbrokerapi.service_broker import OperationState
from tests import factories


def test_last_operation_without_id_fails(client):
    pass


def test_last_operation_with_unknown_id_fails(client):
    pass


def test_last_operation_with_id_returns_state(client):
    instance = factories.ServiceInstanceFactory.create(id="1234")
    operation_1 = factories.OperationFactory.create(
        service_instance=instance, state=OperationState.FAILED
    )
    operation_2 = factories.OperationFactory.create(
        service_instance=instance, state=OperationState.SUCCEEDED
    )
    pp(operation_1)

    client.get_last_operation("1234", operation_1.id)
    assert "state" in client.response.json
    assert client.response.json["state"] == "failed"

    client.get_last_operation("1234", operation_2.id)
    assert "state" in client.response.json
    assert client.response.json["state"] == "succeeded"
