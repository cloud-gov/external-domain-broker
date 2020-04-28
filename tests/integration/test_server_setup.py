def test_server_runs(client):
    client.get("/ping")
    assert client.response.status_code == 200
    assert client.response.body == "PONG"


def test_pebble_runs(pebble):
    assert pebble.is_running()
