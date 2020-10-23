import pytest

from tests.lib import factories


@pytest.fixture
def cdn_instance(clean_db):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="started-as-cdn-instance",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
    )
    return service_instance


# yeah, a whole file for one test.
# the idea is that later we're going to add this feature,
# so this should make it easier to find and update this test


def test_cannot_update_cdn_instance_to_alb(client, cdn_instance):
    client.update_instance_to_alb("started-as-cdn-instance")
    assert client.response.status_code >= 400
    assert "not supported" in client.response.json.get("description")
