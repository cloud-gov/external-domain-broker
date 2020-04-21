def provision_instance(client, params=""):
    client.put(
        "/v2/service_instances/1234" + params,
        json={
            "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
            "plan_id": "6f60835c-8964-4f1f-a19a-579fb27ce694",
            "organization_guid": "abc",
            "space_guid": "123",
        },
    )


def get_last_operation(client):
    client.get("/v2/service_instances/1234/last_operation",)


def test_refuses_to_provision_synchronously(client):
    provision_instance(client, "?accepts_incomplete=false")
    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_synchronously_by_default(client):
    provision_instance(client)
    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_starts_instance_provisioning(client):
    provision_instance(client, "?accepts_incomplete=true")
    assert "AsyncRequired" not in client.response.body
    assert client.response.status_code == 202

    get_last_operation(client)
    assert "state" in client.response.json
    assert client.response.json["state"] == "in progress"
