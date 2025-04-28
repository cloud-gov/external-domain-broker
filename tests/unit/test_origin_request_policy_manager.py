import uuid

from broker.aws import cloudfront as cloudfront_svc
from broker.lib.origin_request_policy_manager import OriginRequestPolicyManager


def test_managed_cache_policies(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "AllViewer"}]

    origin_request_policy_manager = OriginRequestPolicyManager(cloudfront_svc)
    cloudfront.expect_list_origin_request_policies("managed", policies)
    assert origin_request_policy_manager.managed_policies == {
        "AllViewer": cache_policy_id,
    }


def test_managed_cache_policies_handles_paging(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "AllViewer"}]
    cloudfront.expect_list_origin_request_policies(
        "managed", policies, next_marker="next"
    )

    policy2_id = str(uuid.uuid4())
    policies = [{"id": policy2_id, "name": "AllViewerAndCloudFrontHeaders-2022-06"}]

    cloudfront.expect_list_origin_request_policies("managed", policies, marker="next")

    origin_request_policy_manager = OriginRequestPolicyManager(cloudfront_svc)

    assert origin_request_policy_manager.managed_policies == {
        "AllViewer": cache_policy_id,
        "AllViewerAndCloudFrontHeaders-2022-06": policy2_id,
    }


def test_managed_cache_policies_ignores_unknown_policies(cloudfront, cache_policy_id):
    policies = [
        {"id": cache_policy_id, "name": "AllViewer"},
        {"id": "id-1", "name": "FoobarPolicy"},
    ]

    origin_request_policy_manager = OriginRequestPolicyManager(cloudfront_svc)
    cloudfront.expect_list_origin_request_policies("managed", policies)
    assert origin_request_policy_manager.managed_policies == {
        "AllViewer": cache_policy_id,
    }


def test_managed_cache_policies_returns_saved_results(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "AllViewer"}]

    origin_request_policy_manager = OriginRequestPolicyManager(cloudfront_svc)
    cloudfront.expect_list_origin_request_policies("managed", policies)
    policies = origin_request_policy_manager.managed_policies
    # second call should not cause an API request
    policies = origin_request_policy_manager.managed_policies
    assert policies == {
        "AllViewer": cache_policy_id,
    }


def test_get_managed_cache_policy_id(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "AllViewer"}]

    origin_request_policy_manager = OriginRequestPolicyManager(cloudfront_svc)
    cloudfront.expect_list_origin_request_policies("managed", policies)
    assert (
        origin_request_policy_manager.get_managed_policy_id("AllViewer")
        == cache_policy_id
    )
