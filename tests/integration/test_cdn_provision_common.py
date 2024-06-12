import pytest  # noqa F401

from broker.extensions import config, db

from broker.models import (
    CDNDedicatedWAFServiceInstance,
    CDNServiceInstance,
)


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_default_origin_and_path_if_none_provided(
    instance_type, instance_model, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(instance_type, "4321", params={"domains": "example.com"})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = db.session.get(instance_model, "4321")
    assert config.DEFAULT_CLOUDFRONT_ORIGIN == "cloud.local"
    assert instance.cloudfront_origin_hostname == "cloud.local"
    assert instance.cloudfront_origin_path == ""


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_default_cookie_policy_if_none_provided(
    instance_type, instance_model, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(instance_type, "4321", params={"domains": "example.com"})
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_none_cookie_policy(instance_type, instance_model, client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_type, "4321", params={"domains": "example.com", "forward_cookies": ""}
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "none"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_forward_cookie_policy_with_cookies(
    instance_type, instance_model, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_type,
        "4321",
        params={
            "domains": "example.com",
            "forward_cookies": "my_cookie , my_other_cookie",
        },
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "whitelist"
    assert instance.forwarded_cookies == ["my_cookie", "my_other_cookie"]


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_forward_cookie_policy_with_star(
    instance_type, instance_model, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_type, "4321", params={"domains": "example.com", "forward_cookies": "*"}
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_forward_headers_to_host_when_none_specified(
    instance_type, instance_model, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(instance_type, "4321", params={"domains": "example.com"})
    instance = db.session.get(instance_model, "4321")
    assert instance.forwarded_headers == ["HOST"]


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_forward_headers_plus_host_when_some_specified(
    instance_type, instance_model, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_type,
        "4321",
        params={
            "domains": "example.com",
            "forward_headers": "x-my-header,x-your-header",
        },
    )
    instance = db.session.get(instance_model, "4321")
    assert sorted(instance.forwarded_headers) == sorted(
        ["HOST", "X-MY-HEADER", "X-YOUR-HEADER"]
    )


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_does_not_set_host_header_when_using_custom_origin(
    instance_type, instance_model, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_type,
        "4321",
        params={"domains": "example.com", "origin": "my-origin.example.gov"},
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forwarded_headers == []


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_https_only_by_default(
    instance_type, instance_model, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(instance_type, "4321", params={"domains": "example.com"})
    instance = db.session.get(instance_model, "4321")
    assert instance.origin_protocol_policy == "https-only"


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_http_when_set(instance_type, instance_model, client, dns):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_type,
        "4321",
        params={
            "domains": "example.com",
            "origin": "origin.gov",
            "insecure_origin": True,
        },
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.origin_protocol_policy == "http-only"


@pytest.mark.parametrize(
    "instance_type",
    ["cdn", "cdn_dedicated_waf"],
)
def test_provision_refuses_insecure_origin_for_default_origin(
    instance_type, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_type,
        "4321",
        params={"domains": "example.com", "insecure_origin": True},
    )
    desc = client.response.json.get("description")
    assert "insecure_origin" in desc
    assert client.response.status_code == 400


@pytest.mark.parametrize(
    "instance_type, instance_model",
    [
        ("cdn", CDNServiceInstance),
        ("cdn_dedicated_waf", CDNDedicatedWAFServiceInstance),
    ],
)
def test_provision_sets_custom_error_responses(
    instance_type, instance_model, client, dns
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_type,
        "4321",
        params={
            "domains": "example.com",
            "error_responses": {"404": "/errors/404.html"},
        },
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.error_responses["404"] == "/errors/404.html"
