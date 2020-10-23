import pytest

from tests.lib import factories


@pytest.fixture
def migration_instance(clean_db):
    service_instance = factories.MigrationServiceInstanceFactory.create(
        id="started-as-migration-instance", domain_names=["example.com", "foo.com"]
    )
    return service_instance


@pytest.fixture
def full_update_example():
    params = {}
    params["origin"] = "origin.example.com"
    params["path"] = "/not/the/default"
    params["forwarded_cookies"] = ["my-cookie", "my-other-cookie"]
    params["forward_cookie_policy"] = "whitelist"
    params["forwarded_headers"] = ["my-header", "my-other-header"]
    params["insecure_origin"] = False
    params["error_responses"] = {"404": "/404.html"}
    params["cloudfront_distribution_id"] = "ACLOUDFRONTID"
    params["cloudfront_distribution_arn"] = "arn:aws:whatever"
    return params


# yeah, a whole file for one test.
# the idea is that later we're going to add this feature,
# so this should make it easier to find and update this test


@pytest.mark.parametrize(
    "missing_param",
    [
        "origin",
        "path",
        "forwarded_cookies",
        "forward_cookie_policy",
        "forwarded_headers",
        "insecure_origin",
        "error_responses",
        "cloudfront_distribution_id",
        "cloudfront_distribution_arn",
    ],
)
def test_migration_update_fails_without_required_params(
    client, migration_instance, missing_param, full_update_example
):
    full_update_example.pop(missing_param)
    client.update_instance_to_cdn(
        "started-as-migration-instance", params=full_update_example
    )
    assert client.response.status_code >= 400
    assert "missing" in client.response.json.get("description").lower()
    assert missing_param in client.response.json.get("description")
