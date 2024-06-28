import pytest

from broker.models import (
    ALBServiceInstance,
    MigrationServiceInstance,
    DedicatedALBServiceInstance,
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
)


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
def test_refuses_to_deprovision_synchronously(client, instance_model):
    client.deprovision_instance(instance_model, "1234", accepts_incomplete="false")

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
def test_refuses_to_deprovision_synchronously_by_default(instance_model, client):
    client.deprovision_instance(instance_model, "1234", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422
