import pytest

from tests.lib import factories


@pytest.fixture
def alb_instance(clean_db):
    service_instance = factories.ALBServiceInstanceFactory.create(
        id="started-as-alb-instance", domain_names=["example.com", "foo.com"]
    )
    return service_instance


# yeah, a whole file for one test.
# the idea is that later we're going to add this feature,
# so this should make it easier to find and update this test


def test_cannot_update_alb_instance_to_cdn(client, alb_instance):
    client.update_instance_to_cdn("started-as-alb-instance")
    assert client.response.status_code >= 400
    assert "not supported" in client.response.json.get("description")
