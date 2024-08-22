import pytest  # noqa F401

from broker.extensions import config, db

from broker.models import (
    CDNDedicatedWAFServiceInstance,
    CDNServiceInstance,
)


# @pytest.fixture
# def provisioned_instance_client(
#     client, dns, organization_guid, space_guid, instance_model
# ):

#     yield client


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_default_origin_and_path_if_none_provided(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={"domains": "example.com"},
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = db.session.get(instance_model, "4321")
    assert config.DEFAULT_CLOUDFRONT_ORIGIN == "cloud.local"
    assert instance.cloudfront_origin_hostname == "cloud.local"
    assert instance.cloudfront_origin_path == ""


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_default_cookie_policy_if_none_provided(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={"domains": "example.com"},
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_none_cookie_policy(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={"domains": "example.com", "forward_cookies": ""},
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "none"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_forward_cookie_policy_with_cookies(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={
            "domains": "example.com",
            "forward_cookies": "my_cookie , my_other_cookie",
        },
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "whitelist"
    assert instance.forwarded_cookies == ["my_cookie", "my_other_cookie"]


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_forward_cookie_policy_with_star(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={"domains": "example.com", "forward_cookies": "*"},
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_forward_headers_to_host_when_none_specified(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={"domains": "example.com"},
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forwarded_headers == ["HOST"]


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_forward_headers_plus_host_when_some_specified(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={
            "domains": "example.com",
            "forward_headers": "x-my-header,x-your-header",
        },
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert sorted(instance.forwarded_headers) == sorted(
        ["HOST", "X-MY-HEADER", "X-YOUR-HEADER"]
    )


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_does_not_set_host_header_when_using_custom_origin(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={"domains": "example.com", "origin": "my-origin.example.gov"},
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forwarded_headers == []


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_https_only_by_default(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={"domains": "example.com"},
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.origin_protocol_policy == "https-only"


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_http_when_set(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={
            "domains": "example.com",
            "origin": "origin.gov",
            "insecure_origin": True,
        },
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.origin_protocol_policy == "http-only"


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_refuses_insecure_origin_for_default_origin(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={"domains": "example.com", "insecure_origin": True},
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    desc = client.response.json.get("description")
    assert "insecure_origin" in desc
    assert client.response.status_code == 400


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_custom_error_responses(
    dns, client, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={
            "domains": "example.com",
            "error_responses": {"404": "/errors/404.html"},
        },
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.error_responses["404"] == "/errors/404.html"
