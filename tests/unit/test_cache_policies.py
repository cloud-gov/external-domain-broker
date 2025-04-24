import uuid

from broker.aws import cloudfront as cloudfront_svc
from broker.lib.cache_policy_manager import CachePolicyManager


def test_get_managed_cache_policies(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "CachingDisabled"}]

    cache_policies = CachePolicyManager(cloudfront_svc)
    cloudfront.expect_list_cache_policies("managed", policies)
    policies = cache_policies.get_managed_cache_policies()
    assert policies == {
        "CachingDisabled": cache_policy_id,
    }


def test_get_managed_cache_policies_ignores_unknown_policies(
    cloudfront, cache_policy_id
):
    policies = [
        {"id": cache_policy_id, "name": "CachingDisabled"},
        {"id": "id-1", "name": "FoobarPolicy"},
    ]

    cache_policies = CachePolicyManager(cloudfront_svc)
    cloudfront.expect_list_cache_policies("managed", policies)
    policies = cache_policies.get_managed_cache_policies()
    assert policies == {
        "CachingDisabled": cache_policy_id,
    }


def test_get_managed_cache_policies_returns_saved_results(cloudfront, cache_policy_id):
    policies = [{"id": cache_policy_id, "name": "CachingDisabled"}]

    cache_policies = CachePolicyManager(cloudfront_svc)
    cloudfront.expect_list_cache_policies("managed", policies)
    policies = cache_policies.get_managed_cache_policies()
    # second call should not cause an API request
    policies = cache_policies.get_managed_cache_policies()
    assert policies == {
        "CachingDisabled": cache_policy_id,
    }
