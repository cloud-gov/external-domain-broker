import pytest  # noqa F401
from openbrokerapi import errors

from broker.extensions import config, db

from broker.models import (
    CDNDedicatedWAFServiceInstance,
    CDNServiceInstance,
)


@pytest.fixture
def provision_params():
    return {"domains": "example.com", "alarm_notification_email": "foo@bar.com"}


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_default_origin_and_path_if_none_provided(
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    provision_params.update({"forward_cookies": ""})
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    provision_params.update({"forward_cookies": "my_cookie , my_other_cookie"})
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    provision_params.update({"forward_cookies": "*"})
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    provision_params.update({"forward_headers": "x-my-header,x-your-header"})
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    provision_params.update({"origin": "my-origin.example.gov"})
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    provision_params.update(
        {
            "origin": "origin.gov",
            "insecure_origin": True,
        }
    )
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    provision_params.update(
        {
            "insecure_origin": True,
        }
    )
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
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
    dns,
    client,
    organization_guid,
    space_guid,
    provision_params,
    instance_model,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    provision_params.update({"error_responses": {"404": "/errors/404.html"}})
    client.provision_instance(
        instance_model,
        "4321",
        params=provision_params,
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.error_responses["404"] == "/errors/404.html"


@pytest.mark.parametrize(
    "instance_model, alarm_notification_email_param, expected_alarm_notification_email",
    [
        [CDNServiceInstance, "foo@bar.com", None],
        [CDNDedicatedWAFServiceInstance, "foo@bar.com", "foo@bar.com"],
    ],
)
def test_provision_sets_alarm_notification_email(
    dns,
    client,
    organization_guid,
    space_guid,
    instance_model,
    service_instance_id,
    provision_params,
    alarm_notification_email_param,
    expected_alarm_notification_email,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    provision_params.update(
        {
            "alarm_notification_email": alarm_notification_email_param,
        }
    )
    client.provision_instance(
        instance_model,
        service_instance_id,
        params=provision_params,
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    instance = db.session.get(instance_model, service_instance_id)
    alarm_notification_email = (
        instance.alarm_notification_email
        if hasattr(instance, "alarm_notification_email")
        else None
    )
    assert alarm_notification_email == expected_alarm_notification_email


@pytest.mark.parametrize(
    "instance_model, response_status_code",
    [
        [CDNServiceInstance, 202],
        [CDNDedicatedWAFServiceInstance, 400],
    ],
)
def test_provision_no_alarm_notification_email(
    dns,
    client,
    organization_guid,
    space_guid,
    instance_model,
    provision_params,
    service_instance_id,
    response_status_code,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")

    provision_params["alarm_notification_email"] = None

    client.provision_instance(
        instance_model,
        service_instance_id,
        params=provision_params,
        organization_guid=organization_guid,
        space_guid=space_guid,
    )

    assert client.response.status_code == response_status_code
