from openbrokerapi.service_broker import OperationState
from tests import factories


def test_last_operation_without_id_fails(client):
    factories.ServiceInstanceFactory.create(id="1234")
    client.get_last_operation("1234", None)
    assert "Missing operation" in client.response.body
    assert client.response.status_code == 400


def test_last_operation_with_unknown_id_fails(client):
    factories.ServiceInstanceFactory.create(id="1234")
    client.get_last_operation("1234", "9000")
    assert "Invalid" in client.response.body
    assert client.response.status_code == 400


def test_last_operation_with_id_returns_state(client):
    instance = factories.ServiceInstanceFactory.create(id="1234")
    operation_1 = factories.OperationFactory.create(
        service_instance=instance, state=OperationState.FAILED
    )
    operation_2 = factories.OperationFactory.create(
        service_instance=instance, state=OperationState.SUCCEEDED
    )

    client.get_last_operation("1234", operation_1.id)
    assert client.response.json.get("state") == "failed"

    client.get_last_operation("1234", operation_2.id)
    assert client.response.json.get("state") == "succeeded"
