import pytest  # noqa F401

from broker.models import Operation
from tests.lib import factories


def test_last_operation_without_id_fails(client):
    factories.CDNServiceInstanceFactory.create(id="1234")
    client.get_last_operation("1234", None)
    assert "Missing operation" in client.response.body
    assert client.response.status_code == 400


def test_last_operation_with_unknown_id_fails(client):
    factories.CDNServiceInstanceFactory.create(id="1234")
    client.get_last_operation("1234", "9000")
    assert "Invalid" in client.response.body
    assert client.response.status_code == 400


def test_last_operation_with_id_returns_state(client):
    instance = factories.CDNServiceInstanceFactory.create(id="1234")
    operation_1 = factories.OperationFactory.create(
        service_instance=instance, state=Operation.States.FAILED.value
    )
    operation_2 = factories.OperationFactory.create(
        service_instance=instance, state=Operation.States.SUCCEEDED.value
    )

    client.get_last_operation("1234", operation_1.id)
    assert client.response.json.get("state") == "failed"

    client.get_last_operation("1234", operation_2.id)
    assert client.response.json.get("state") == "succeeded"
