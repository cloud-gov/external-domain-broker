import pytest


def test_server_runs(client):
    client.get("/ping")
    assert client.response.status_code == 200
    assert client.response.body == "PONG"
