def test_refuses_to_provision_synchronously(client):
    client.provision_instance(accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_synchronously_by_default(client):
    client.provision_instance(accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_starts_instance_provisioning(client):
    client.provision_instance(accepts_incomplete="true")

    assert "AsyncRequired" not in client.response.body
    assert client.response.status_code == 202

    client.get_last_operation()

    assert "state" in client.response.json
    assert client.response.json["state"] == "in progress"
