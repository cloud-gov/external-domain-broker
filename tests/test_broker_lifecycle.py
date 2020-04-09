import pytest

from broker.broker import Broker

def catalog():
    return Broker().catalog()


def test_catalog_has_top_level_values():
    assert catalog().id is not None
    assert catalog().name == "custom-domain"
    assert "domain" in catalog().description
    assert "domain" in catalog().metadata.displayName
    assert "domain" in catalog().metadata.longDescription
    assert catalog().metadata.supportUrl == "https://cloud.gov/support"
    assert catalog().metadata.providerDisplayName == "Cloud.gov"


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
