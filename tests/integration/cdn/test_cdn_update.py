import json
from datetime import date, datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import Challenge, Operation, CDNServiceInstance
from tests.lib import factories
from tests.lib.client import check_last_operation_description


@pytest.fixture
def service_instance():
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        private_key_pem="SOMEPRIVATEKEY",
        origin_protocol_policy="https-only",
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        service_instance=service_instance,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        service_instance=service_instance,
    )
    db.session.refresh(service_instance)
    return service_instance


def test_refuses_to_update_synchronously(client):
    client.update_cdn_instance("4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_update_synchronously_by_default(client):
    client.update_cdn_instance("4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_update_with_duplicate_domains(client, dns, service_instance):
    factories.CDNServiceInstanceFactory.create(domain_names=["foo.com", "bar.com"])
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.update_cdn_instance("4321", params={"domains": "example.com, foo.com"})

    assert "already exists" in client.response.body, client.response.body
    assert client.response.status_code == 400, client.response.body


def test_duplicate_domain_check_ignores_self(client, dns, service_instance):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.update_cdn_instance("4321", params={"domains": "example.com, foo.com"})

    assert client.response.status_code == 202, client.response.body


def test_duplicate_domain_check_ignores_deactivated(client, dns, service_instance):
    factories.CDNServiceInstanceFactory.create(
        domain_names="foo.com", deactivated_at=datetime.utcnow()
    )
    dns.add_cname("_acme-challenge.foo.com")

    client.update_cdn_instance("4321", params={"domains": "foo.com"})

    assert client.response.status_code == 202, client.response.body


def test_refuses_to_update_without_any_acme_challenge_CNAMEs(client, service_instance):
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com " in desc
    assert "_acme-challenge.foo.com.domains.cloud.test" in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_update_without_one_acme_challenge_CNAME(
    client, dns, service_instance
):
    dns.add_cname("_acme-challenge.foo.com")
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com" not in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_update_with_incorrect_acme_challenge_CNAME(
    client, dns, service_instance
):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com", target="INCORRECT")
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")

    assert "is set incorrectly" in desc

    assert " _acme-challenge.foo.com " in desc
    assert " _acme-challenge.foo.com.domains.cloud.test" in desc
    assert " INCORRECT" in desc

    assert " _acme-challenge.bar.com" not in desc
    assert client.response.status_code == 400


def test_refuses_update_for_canceled_instance(client, dns, clean_db, service_instance):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    service_instance.deactivated_at = datetime.now()
    db.session.add(service_instance)
    db.session.commit()

    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "canceled" in desc
    assert client.response.status_code == 400


def test_refuses_update_for_nonexistent_instance(client, dns):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})
    desc = client.response.json.get("description")
    assert "does not exist" in desc
    assert client.response.status_code == 400


def test_refuses_update_for_instance_with_operation(client, dns, service_instance):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com")
    factories.OperationFactory.create(service_instance=service_instance)
    client.update_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")

    assert "in progress" in desc
    assert client.response.status_code == 400


def test_provision_sets_default_origin_if_provided_as_none(
    client, dns, service_instance
):
    client.update_cdn_instance("4321", params={"origin": None})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = CDNServiceInstance.query.get("4321")
    assert config.DEFAULT_CLOUDFRONT_ORIGIN == "cloud.local"
    assert instance.cloudfront_origin_hostname == "cloud.local"

    # make sure nothing else got changed
    assert instance.cloudfront_origin_path == "origin_path"
    assert sorted(instance.domain_names) == sorted(["foo.com", "example.com"])
    assert "HOST" in instance.forwarded_headers


def test_provision_sets_default_origin_path_if_provided_as_none(
    client, dns, service_instance
):
    client.update_cdn_instance("4321", params={"path": None})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = CDNServiceInstance.query.get("4321")
    assert instance.cloudfront_origin_path == ""

    # make sure nothing else got changed
    assert instance.cloudfront_origin_hostname == "origin_hostname"
    assert sorted(instance.domain_names) == sorted(["foo.com", "example.com"])


def test_update_sets_default_cookie_policy_if_provided_as_none(
    client, dns, service_instance
):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()

    client.update_cdn_instance("4321", params={"forward_cookies": None})
    db.session.expunge_all()
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


def test_update_sets_none_cookie_policy(client, dns, service_instance):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()
    client.update_cdn_instance("4321", params={"forward_cookies": ""})
    db.session.expunge_all()
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "none"
    assert instance.forwarded_cookies == []


def test_update_sets_forward_cookie_policy_with_cookies(client, dns, service_instance):
    client.update_cdn_instance(
        "4321", params={"forward_cookies": "my_cookie , my_other_cookie"}
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "whitelist"
    assert instance.forwarded_cookies == ["my_cookie", "my_other_cookie"]


def test_update_sets_forward_cookie_policy_with_star(client, dns, service_instance):
    service_instance.forward_cookie_policy = "whitelist"
    service_instance.forwarded_cookies = ["foo", "bar"]
    db.session.add(service_instance)
    db.session.commit()
    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance(
        "4321", params={"domains": "example.com", "forward_cookies": "*"}
    )
    db.session.expunge_all()
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


def test_update_sets_forward_headers_to_host_when_specified_as_none(
    client, dns, service_instance
):
    service_instance.cloudfront_origin_hostname = config.DEFAULT_CLOUDFRONT_ORIGIN
    service_instance.cloudfront_origin_path = ""
    service_instance.forwarded_headers = ["HOST", "x-my-header"]
    db.session.add(service_instance)
    db.session.commit()

    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance("4321", params={"forward_headers": None})
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forwarded_headers == ["HOST"]


def test_update_sets_forward_headers_plus_host_when_some_specified(
    client, dns, service_instance
):
    service_instance.cloudfront_origin_hostname = config.DEFAULT_CLOUDFRONT_ORIGIN
    service_instance.cloudfront_origin_path = ""
    service_instance.forwarded_headers = ["HOST"]
    db.session.add(service_instance)
    db.session.commit()

    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance(
        "4321", params={"forward_headers": "x-my-header,x-your-header"}
    )
    instance = CDNServiceInstance.query.get("4321")
    assert sorted(instance.forwarded_headers) == sorted(
        ["HOST", "x-my-header", "x-your-header"]
    )


def test_update_does_not_set_host_header_when_using_custom_origin(
    client, dns, service_instance
):
    dns.add_cname("_acme-challenge.example.com")
    service_instance.forwarded_headers = ["x-my-header"]
    db.session.add(service_instance)
    db.session.commit()

    client.update_cdn_instance("4321", params={"forward_headers": None})
    instance = CDNServiceInstance.query.get("4321")
    assert instance.forwarded_headers == []


def test_update_sets_http_when_set(client, dns, service_instance):
    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance(
        "4321", params={"origin": "origin.gov", "insecure_origin": True}
    )
    instance = CDNServiceInstance.query.get("4321")
    assert instance.origin_protocol_policy == "http-only"


def test_update_refuses_insecure_origin_for_default_origin(
    client, dns, service_instance
):
    dns.add_cname("_acme-challenge.example.com")
    client.update_cdn_instance("4321", params={"origin": None, "insecure_origin": True})
    desc = client.response.json.get("description")
    assert client.response.status_code == 400
    assert "insecure_origin" in desc
