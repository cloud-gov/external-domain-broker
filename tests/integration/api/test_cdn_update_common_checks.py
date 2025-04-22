from datetime import datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
)

from tests.lib import factories


@pytest.fixture
def params_with_alarm_notification_email():
    return {"alarm_notification_email": "fake@localhost"}


@pytest.fixture()
def service_instance_factory(instance_model):
    if instance_model == CDNDedicatedWAFServiceInstance:
        return factories.CDNDedicatedWAFServiceInstanceFactory
    elif instance_model == CDNServiceInstance:
        return factories.CDNServiceInstanceFactory


@pytest.fixture
def service_instance(service_instance_factory):
    service_instance = service_instance_factory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
    )
    new_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1002,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_arn="certificate_arn",
        iam_server_certificate_name="certificate_name",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1001,
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=1001,
        answered=True,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=1001,
        answered=True,
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=1002,
        answered=False,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=1002,
        answered=False,
    )
    service_instance.current_certificate = current_cert
    service_instance.new_certificate = new_cert
    db.session.add(service_instance)
    db.session.add(current_cert)
    db.session.add(new_cert)
    db.session.commit()
    return service_instance


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_default_origin_if_provided_as_none(
    instance_model,
    client,
    params_with_alarm_notification_email,
    service_instance,
):
    params_with_alarm_notification_email.update({"origin": None})
    client.update_instance(
        instance_model, "4321", params=params_with_alarm_notification_email
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = db.session.get(instance_model, "4321")
    assert config.DEFAULT_CLOUDFRONT_ORIGIN == "cloud.local"
    assert instance.cloudfront_origin_hostname == "cloud.local"

    # make sure nothing else got changed
    assert instance.cloudfront_origin_path == "origin_path"
    assert sorted(instance.domain_names) == sorted(["foo.com", "example.com"])
    assert "HOST" in instance.forwarded_headers


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_default_origin_path_if_provided_as_none(
    instance_model, client, params_with_alarm_notification_email, service_instance
):
    params_with_alarm_notification_email.update({"path": None})
    client.update_instance(
        instance_model, "4321", params=params_with_alarm_notification_email
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = db.session.get(instance_model, "4321")
    assert instance.cloudfront_origin_path == ""

    # make sure nothing else got changed
    assert instance.cloudfront_origin_hostname == "origin_hostname"
    assert sorted(instance.domain_names) == sorted(["foo.com", "example.com"])


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_default_cookie_policy_if_provided_as_none(
    instance_model, client, params_with_alarm_notification_email, service_instance
):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()

    params_with_alarm_notification_email.update({"forward_cookies": None})
    client.update_instance(
        instance_model, "4321", params=params_with_alarm_notification_email
    )
    db.session.expunge_all()
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_none_cookie_policy(
    instance_model, client, params_with_alarm_notification_email, service_instance
):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()
    params_with_alarm_notification_email.update({"forward_cookies": ""})
    client.update_instance(
        instance_model, "4321", params=params_with_alarm_notification_email
    )
    db.session.expunge_all()
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "none"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_forward_cookie_policy_with_cookies(
    instance_model, client, service_instance
):
    client.update_instance(
        instance_model,
        "4321",
        params={"forward_cookies": "my_cookie , my_other_cookie"},
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "whitelist"
    assert instance.forwarded_cookies == ["my_cookie", "my_other_cookie"]


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_forward_cookie_policy_with_star(
    instance_model, client, dns, params_with_alarm_notification_email, service_instance
):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()
    dns.add_cname("_acme-challenge.example.com")

    params_with_alarm_notification_email.update(
        {"domains": "example.com", "forward_cookies": "*"}
    )
    client.update_instance(
        instance_model,
        "4321",
        params=params_with_alarm_notification_email,
    )
    db.session.expunge_all()
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_forward_headers_to_host_when_specified_as_none(
    instance_model, client, dns, service_instance
):
    service_instance.cloudfront_origin_hostname = config.DEFAULT_CLOUDFRONT_ORIGIN
    service_instance.cloudfront_origin_path = ""
    service_instance.forwarded_headers = ["HOST", "x-my-header"]
    db.session.add(service_instance)
    db.session.commit()

    dns.add_cname("_acme-challenge.example.com")
    client.update_instance(instance_model, "4321", params={"forward_headers": None})
    instance = db.session.get(instance_model, "4321")
    assert instance.forwarded_headers == ["HOST"]


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_forward_headers_plus_host_when_some_specified(
    instance_model, client, dns, service_instance
):
    service_instance.cloudfront_origin_hostname = config.DEFAULT_CLOUDFRONT_ORIGIN
    service_instance.cloudfront_origin_path = ""
    service_instance.forwarded_headers = ["HOST"]
    db.session.add(service_instance)
    db.session.commit()

    dns.add_cname("_acme-challenge.example.com")
    client.update_instance(
        instance_model, "4321", params={"forward_headers": "x-my-header,x-your-header"}
    )
    instance = db.session.get(instance_model, "4321")
    assert sorted(instance.forwarded_headers) == sorted(
        ["HOST", "X-MY-HEADER", "X-YOUR-HEADER"]
    )


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_does_not_set_host_header_when_using_custom_origin(
    instance_model, client, dns, service_instance
):
    dns.add_cname("_acme-challenge.example.com")
    service_instance.forwarded_headers = ["x-my-header"]
    db.session.add(service_instance)
    db.session.commit()

    client.update_instance(instance_model, "4321", params={"forward_headers": None})
    instance = db.session.get(instance_model, "4321")
    assert instance.forwarded_headers == []


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_http_when_set(instance_model, client, dns, service_instance):
    dns.add_cname("_acme-challenge.example.com")
    client.update_instance(
        instance_model, "4321", params={"origin": "origin.gov", "insecure_origin": True}
    )
    instance = db.session.get(instance_model, "4321")
    assert instance.origin_protocol_policy == "http-only"


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_refuses_insecure_origin_for_default_origin(
    instance_model, client, dns, service_instance
):
    dns.add_cname("_acme-challenge.example.com")
    client.update_instance(
        instance_model, "4321", params={"origin": None, "insecure_origin": True}
    )
    desc = client.response.json.get("description")
    assert client.response.status_code == 400
    assert "insecure_origin" in desc


@pytest.mark.parametrize(
    "instance_model, alarm_notification_email_param, expected_alarm_notification_email",
    [
        [CDNServiceInstance, "foo@bar.com", None],
        [CDNDedicatedWAFServiceInstance, "foo@bar.com", "foo@bar.com"],
    ],
)
def test_update_sets_alarm_notification_email(
    dns,
    client,
    instance_model,
    alarm_notification_email_param,
    expected_alarm_notification_email,
    service_instance,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    client.update_instance(
        instance_model,
        service_instance.id,
        params={
            "domains": ["example.com"],
            "alarm_notification_email": alarm_notification_email_param,
        },
    )
    instance = db.session.get(instance_model, service_instance.id)
    alarm_notification_email = (
        instance.alarm_notification_email
        if hasattr(instance, "alarm_notification_email")
        else None
    )
    assert alarm_notification_email == expected_alarm_notification_email


@pytest.mark.parametrize(
    "instance_model, expected_response_status",
    [
        [CDNServiceInstance, 202],
        [CDNDedicatedWAFServiceInstance, 400],
    ],
)
def test_update_no_alarm_notification_email(
    dns,
    client,
    instance_model,
    expected_response_status,
    service_instance,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    client.update_instance(
        instance_model,
        service_instance.id,
        params={
            "domains": ["example.com"],
        },
    )
    assert client.response.status_code == expected_response_status


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_cache_policy_id(
    dns,
    client,
    instance_model,
    service_instance,
    cache_policy_id,
    cloudfront,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    cache_policies = [{"id": cache_policy_id, "name": "CachingDisabled"}]

    # Request to fetch cache policies is cached, so only happens once for
    # both test runs
    if instance_model == CDNServiceInstance:
        cloudfront.expect_list_cache_policies("managed", cache_policies)

    client.update_instance(
        instance_model,
        service_instance.id,
        params={
            "domains": ["example.com"],
            "cache_policy": "CachingDisabled",
            "alarm_notification_email": "foo@bar",
        },
    )

    assert client.response.status_code == 202

    instance = db.session.get(instance_model, service_instance.id)
    assert cache_policy_id == instance.cache_policy_id
