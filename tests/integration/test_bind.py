import pytest


@pytest.mark.focus
def test_catalog_advertises_non_bindable(client):
    client.get_catalog()
    assert "services" in client.response.json
    first_service = client.response.json["services"][0]
    assert "bindable" in first_service
    assert first_service["bindable"] is False
