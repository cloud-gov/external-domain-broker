import pytest

from broker.api import API


@pytest.fixture()
def catalog():
    return API().catalog()


def test_catalog_has_top_level_values(catalog):
    assert catalog.id is not None
    assert catalog.name == "external-domain"
    assert "domain" in catalog.description
    assert "domain" in catalog.metadata.displayName
    assert "domain" in catalog.metadata.longDescription
    assert catalog.metadata.supportUrl == "https://cloud.gov/support"
    assert catalog.metadata.providerDisplayName == "Cloud.gov"


def test_catalog_has_correct_plans(catalog):
    assert catalog.plans is not []
    alb_plan = catalog.plans[0]
    cloudfront_plan = catalog.plans[1]
    migration_plan = catalog.plans[2]
    dedicated_alb_plan = catalog.plans[3]

    assert alb_plan.id is not None
    assert alb_plan.id != ""
    assert alb_plan.name == "domain"
    assert "domain" in alb_plan.description

    assert cloudfront_plan.id is not None
    assert cloudfront_plan.id != ""
    assert cloudfront_plan.name == "domain-with-cdn"
    assert "CloudFront" in cloudfront_plan.description

    assert migration_plan.id is not None
    assert migration_plan.id != ""
    assert migration_plan.name == "migration-not-for-direct-use"
    assert "Migration" in migration_plan.description
    assert migration_plan.plan_updateable

    assert dedicated_alb_plan.id is not None
    assert dedicated_alb_plan.id != ""
    assert dedicated_alb_plan.name == "domain-with-org-lb"
    assert "domain" in alb_plan.description

    assert cloudfront_plan.id != alb_plan.id
    assert cloudfront_plan.id != migration_plan.id
    assert migration_plan.id != alb_plan.id
