import pytest

from tests.lib import factories


@pytest.fixture
def migration_instance(clean_db):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="started-as-migration-instance", domain_names=["example.com", "foo.com"]
    )
    return service_instance


# yeah, a whole file for one test.
# the idea is that later we're going to add this feature,
# so this should make it easier to find and update this test


def test_cannot_update_migration_instance_to_alb(client, migration_instance):
    client.update_instance_to_alb("started-as-migration-instance")
    assert client.response.status_code >= 400
    assert "not supported" in client.response.json.get("description")
