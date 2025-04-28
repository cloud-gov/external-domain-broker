import uuid

from broker.aws import cloudfront as cloudfront_svc
from broker.lib.cache_policy_manager import CachePolicyManager


def test_managed_cache_policies(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "CachingDisabled"}]

    cache_policy_manager = CachePolicyManager(cloudfront_svc)
    cloudfront.expect_list_cache_policies("managed", policies)
    assert cache_policy_manager.managed_policies == {
        "CachingDisabled": cache_policy_id,
    }


def test_managed_cache_policies_handles_paging(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "CachingDisabled"}]
    cloudfront.expect_list_cache_policies("managed", policies, next_marker="next")

    policy2_id = str(uuid.uuid4())
    policies = [{"id": policy2_id, "name": "CachingOptimized"}]

    cloudfront.expect_list_cache_policies("managed", policies, marker="next")

    cache_policy_manager = CachePolicyManager(cloudfront_svc)

    assert cache_policy_manager.managed_policies == {
        "CachingDisabled": cache_policy_id,
        "CachingOptimized": policy2_id,
    }


def test_managed_cache_policies_ignores_unknown_policies(cloudfront, cache_policy_id):
    policies = [
        {"id": cache_policy_id, "name": "CachingDisabled"},
        {"id": "id-1", "name": "FoobarPolicy"},
    ]

    cache_policy_manager = CachePolicyManager(cloudfront_svc)
    cloudfront.expect_list_cache_policies("managed", policies)
    assert cache_policy_manager.managed_policies == {
        "CachingDisabled": cache_policy_id,
    }


def test_managed_cache_policies_returns_saved_results(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "CachingDisabled"}]

    cache_policy_manager = CachePolicyManager(cloudfront_svc)
    cloudfront.expect_list_cache_policies("managed", policies)
    policies = cache_policy_manager.managed_policies
    # second call should not cause an API request
    policies = cache_policy_manager.managed_policies
    assert policies == {
        "CachingDisabled": cache_policy_id,
    }


def test_get_managed_cache_policy_id(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "CachingDisabled"}]

    cache_policy_manager = CachePolicyManager(cloudfront_svc)
    cloudfront.expect_list_cache_policies("managed", policies)
    assert (
        cache_policy_manager.get_managed_policy_id("CachingDisabled") == cache_policy_id
    )
