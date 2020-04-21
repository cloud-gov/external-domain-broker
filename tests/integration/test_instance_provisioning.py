def test_refuses_to_provision_synchronously(client):
    client.put(
        "/v2/service_instances/1234?accepts_incomplete=false",
        json={
            "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
            "plan_id": "6f60835c-8964-4f1f-a19a-579fb27ce694",
            "organization_guid": "abc",
            "space_guid": "123",
        },
    )
    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_synchronously_by_default(client):
    client.put(
        "/v2/service_instances/1234",
        json={
            "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
            "plan_id": "6f60835c-8964-4f1f-a19a-579fb27ce694",
            "organization_guid": "abc",
            "space_guid": "123",
        },
    )
    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_starts_instance_provisioning(client):
    client.put(
        "/v2/service_instances/1234?accepts_incomplete=true",
        json={
            "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
            "plan_id": "6f60835c-8964-4f1f-a19a-579fb27ce694",
            "organization_guid": "abc",
            "space_guid": "123",
        },
    )
    assert "AsyncRequired" not in client.response.body
    assert client.response.status_code == 202
