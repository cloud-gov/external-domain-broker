from datetime import datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
)

from tests.lib import factories


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
    db.session.expunge_all()
    return service_instance


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_provision_sets_default_origin_if_provided_as_none(
    instance_model, client, service_instance
):
    client.update_instance(instance_model, "4321", params={"origin": None})
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
def test_provision_sets_default_origin_path_if_provided_as_none(
    instance_model, client, service_instance
):
    client.update_instance(instance_model, "4321", params={"path": None})
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
    instance_model, client, service_instance
):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()

    client.update_instance(instance_model, "4321", params={"forward_cookies": None})
    db.session.expunge_all()
    instance = db.session.get(instance_model, "4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


@pytest.mark.parametrize(
    "instance_model",
    [CDNServiceInstance, CDNDedicatedWAFServiceInstance],
)
def test_update_sets_none_cookie_policy(instance_model, client, service_instance):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()
    client.update_instance(instance_model, "4321", params={"forward_cookies": ""})
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
    instance_model, client, dns, service_instance
):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()
    dns.add_cname("_acme-challenge.example.com")
    client.update_instance(
        instance_model,
        "4321",
        params={"domains": "example.com", "forward_cookies": "*"},
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
