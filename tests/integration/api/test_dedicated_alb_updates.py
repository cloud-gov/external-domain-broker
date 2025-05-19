import pytest
from unittest.mock import patch

from broker.aws import cloudfront as real_cloudfront
from broker.extensions import config
from broker.lib import cdn
from broker.lib.cache_policy_manager import CachePolicyManager
from broker.lib.origin_request_policy_manager import OriginRequestPolicyManager
from broker.models import (
    MigrateDedicatedALBToCDNDedicatedWafServiceInstance,
    ServiceInstanceTypes,
)

from tests.lib import factories


@pytest.fixture
def service_instance(clean_db, service_instance_id):
    service_instance = factories.DedicatedALBServiceInstanceFactory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        alb_arn="alb-arn-1",
        alb_listener_arn="alb-listener-arn-1",
        domain_internal="fake1234.cloud.test",
        org_id="org-1",
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
    service_instance.current_certificate = current_cert
    clean_db.session.add(service_instance)
    clean_db.session.add(current_cert)
    clean_db.session.commit()
    return service_instance


@pytest.fixture
def params_with_alarm_notification_email():
    return {"alarm_notification_email": "fake@localhost"}


def test_migrate_cdn_dedicated_waf_no_alarm_notification_email(
    clean_db, client, service_instance
):
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(service_instance.id)
    clean_db.session.expunge_all()

    assert client.response.status_code == 400, client.response.body


def test_migrate_cdn_dedicated_waf_with_alarm_notification_email(
    clean_db, client, service_instance
):
    assert not hasattr(service_instance, "alarm_notification_email")

    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id, params={"alarm_notification_email": "foo@bar.com"}
    )
    clean_db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    service_instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert (
        service_instance.instance_type
        == ServiceInstanceTypes.DEDICATED_ALB_CDN_DEDICATED_WAF_MIGRATION.value
    )
    assert service_instance.alarm_notification_email == "foo@bar.com"


def test_provision_sets_default_origin_and_path_if_none_provided(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
):
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    clean_db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert config.DEFAULT_CLOUDFRONT_ORIGIN == "cloud.local"
    assert instance.cloudfront_origin_hostname == "cloud.local"

    # make sure nothing else got changed
    assert instance.cloudfront_origin_path == ""
    assert sorted(instance.domain_names) == sorted(["foo.com", "example.com"])
    assert "HOST" in instance.forwarded_headers


def test_provision_sets_default_cookie_policy_if_none_provided(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


def test_provision_sets_none_cookie_policy(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    params_with_alarm_notification_email.update({"forward_cookies": ""})
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert instance.forward_cookie_policy == "none"
    assert instance.forwarded_cookies == []


def test_provision_sets_forward_cookie_policy_with_cookies(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    params_with_alarm_notification_email.update(
        {"forward_cookies": "my_cookie , my_other_cookie"}
    )
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert instance.forward_cookie_policy == "whitelist"
    assert instance.forwarded_cookies == ["my_cookie", "my_other_cookie"]


def test_provision_sets_forward_cookie_policy_with_star(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    params_with_alarm_notification_email.update({"forward_cookies": "*"})
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert instance.forward_cookie_policy == "all"
    assert instance.forwarded_cookies == []


def test_provision_sets_forward_headers_to_host_when_none_specified(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert instance.forwarded_headers == ["HOST"]


def test_provision_sets_forward_headers_plus_host_when_some_specified(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    params_with_alarm_notification_email.update(
        {"forward_headers": "x-my-header,x-your-header"}
    )
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert sorted(instance.forwarded_headers) == sorted(
        ["HOST", "X-MY-HEADER", "X-YOUR-HEADER"]
    )


def test_provision_does_not_set_host_header_when_using_custom_origin(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    params_with_alarm_notification_email.update({"origin": "my-origin.example.gov"})
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert instance.forwarded_headers == []


def test_provision_sets_https_only_by_default(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert instance.origin_protocol_policy == "https-only"


def test_provision_sets_http_when_set(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    params_with_alarm_notification_email.update(
        {
            "origin": "origin.gov",
            "insecure_origin": True,
        }
    )
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert instance.origin_protocol_policy == "http-only"


def test_provision_refuses_insecure_origin_for_default_origin(
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    params_with_alarm_notification_email.update(
        {
            "insecure_origin": True,
        }
    )
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    desc = client.response.json.get("description")
    assert "insecure_origin" in desc
    assert client.response.status_code == 400


def test_provision_sets_custom_error_responses(
    clean_db,
    client,
    service_instance,
    params_with_alarm_notification_email,
    dns,
    mocked_cf_api,
):
    dns.add_cname("_acme-challenge.example.com")
    params_with_alarm_notification_email.update(
        {"error_responses": {"404": "/errors/404.html"}}
    )
    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )
    instance = clean_db.session.get(
        MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance.id
    )
    assert instance.error_responses["404"] == "/errors/404.html"


def test_provision_sets_cache_policy(
    dns,
    client,
    params_with_alarm_notification_email,
    service_instance_id,
    cloudfront,
    cache_policy_id,
    clean_db,
    service_instance,
    mocked_cf_api,
):
    params_with_alarm_notification_email.update(
        {
            "cache_policy": "Managed-CachingDisabled",
        }
    )
    dns.add_cname("_acme-challenge.example.com")
    cache_policies = [{"id": cache_policy_id, "name": "Managed-CachingDisabled"}]

    # cache_policy_manager is managed in global state, so that in real API usage
    # it caches the cache policies fetched by AWS. For testing purposes, we mock
    # the cache_policy_manager and re-initialize it in every test so that we can
    # consistently expect it to make mocked requests to AWS
    with patch.object(cdn, "cache_policy_manager", CachePolicyManager(real_cloudfront)):
        cloudfront.expect_list_cache_policies("managed", cache_policies)

        client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
            service_instance.id,
            params=params_with_alarm_notification_email,
        )

        assert client.response.status_code == 202
        instance = clean_db.session.get(
            MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance_id
        )
        assert instance.cache_policy_id == cache_policy_id

        cloudfront.assert_no_pending_responses()


def test_provision_error_invalid_cache_policy(
    dns,
    client,
    params_with_alarm_notification_email,
    cloudfront,
    service_instance,
    mocked_cf_api,
):
    params_with_alarm_notification_email.update(
        {
            "cache_policy": "FakePolicy",
        }
    )
    dns.add_cname("_acme-challenge.example.com")

    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )

    assert client.response.status_code == 400

    cloudfront.assert_no_pending_responses()


def test_provision_sets_origin_request_policy(
    dns,
    client,
    params_with_alarm_notification_email,
    service_instance_id,
    cloudfront,
    origin_request_policy_id,
    clean_db,
    service_instance,
    mocked_cf_api,
):
    params_with_alarm_notification_email.update(
        {
            "origin_request_policy": "Managed-AllViewer",
        }
    )
    dns.add_cname("_acme-challenge.example.com")
    origin_request_policies = [
        {"id": origin_request_policy_id, "name": "Managed-AllViewer"}
    ]

    # origin_request_policy_manager is managed in global state, so that in real API usage
    # it caches the origin request policies fetched by AWS. For testing purposes, we mock
    # the origin_request_policy_manager and re-initialize it in every test so that we can
    # consistently expect it to make mocked requests to AWS
    with patch.object(
        cdn,
        "origin_request_policy_manager",
        OriginRequestPolicyManager(real_cloudfront),
    ):
        cloudfront.expect_list_origin_request_policies(
            "managed", origin_request_policies
        )

        client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
            service_instance.id,
            params=params_with_alarm_notification_email,
        )

        assert client.response.status_code == 202
        instance = clean_db.session.get(
            MigrateDedicatedALBToCDNDedicatedWafServiceInstance, service_instance_id
        )
        assert instance.origin_request_policy_id == origin_request_policy_id

        cloudfront.assert_no_pending_responses()


def test_provision_error_invalid_origin_request_policy(
    dns,
    client,
    params_with_alarm_notification_email,
    service_instance,
    cloudfront,
    mocked_cf_api,
):
    params_with_alarm_notification_email.update(
        {
            "origin_request_policy": "FakePolicy",
        }
    )
    dns.add_cname("_acme-challenge.example.com")

    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance.id,
        params=params_with_alarm_notification_email,
    )

    assert client.response.status_code == 400

    cloudfront.assert_no_pending_responses()
