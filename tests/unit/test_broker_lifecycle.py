from broker.api import API


def catalog():
    return API().catalog()


def test_catalog_has_top_level_values():
    assert catalog().id is not None
    assert catalog().name == "external-domain"
    assert "domain" in catalog().description
    assert "domain" in catalog().metadata.displayName
    assert "domain" in catalog().metadata.longDescription
    assert catalog().metadata.supportUrl == "https://cloud.gov/support"
    assert catalog().metadata.providerDisplayName == "Cloud.gov"


def test_catalog_has_correct_plans():
    assert catalog().plans is not []
    alb_plan = catalog().plans[0]
    cloudfront_plan = catalog().plans[1]

    assert alb_plan.id is not None
    assert alb_plan.id != ""
    assert alb_plan.name == "domain"
    assert "domain" in alb_plan.description

    assert cloudfront_plan.id is not None
    assert cloudfront_plan.id != ""
    assert cloudfront_plan.name == "domain-with-cdn"
    assert "CloudFront" in cloudfront_plan.description

    assert cloudfront_plan.id != alb_plan.id


def test_provision_returns_spec_with_dashboard_id():
    pass


def test_provision_saves_space_and_org_guids():
    pass


def test_bind_returns_api_url_with_credentials():
    pass


def test_bind_saves_binding_with_apikey_in_db():
    pass


def test_unbind_successfully_unbind():
    pass


def test_unbind_deletes_binding():
    pass


def test_deprovision_successfully_deprovision():
    pass


def test_deprovision_deletes_entry():
    pass
