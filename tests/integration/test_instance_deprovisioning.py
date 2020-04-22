def test_starts_instance_deprovisioning(client):
    client.provision_instance(accepts_incomplete="true")
    assert "AsyncRequired" not in client.response.body
    assert client.response.status_code == 202

    client.deprovision_instance()

