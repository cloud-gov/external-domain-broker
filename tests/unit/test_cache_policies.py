import uuid

from broker.aws import cloudfront as cloudfront_svc
from broker.lib.cache_policies import CachePolicies


def test_get_managed_cache_policies(cloudfront):
    policy_id = str(uuid.uuid4())
    policy_name = f"{policy_id}-policy"

    cache_policies = CachePolicies(cloudfront_svc)
    cloudfront.expect_list_cache_policies("managed", policy_id, policy_name)
    policies = cache_policies.get_managed_cache_policies()
    assert policies == {
        policy_name: policy_id,
    }


def test_get_managed_cache_policies_returns_saved_results(cloudfront):
    policy_id = str(uuid.uuid4())
    policy_name = f"{policy_id}-policy"

    cache_policies = CachePolicies(cloudfront_svc)
    cloudfront.expect_list_cache_policies("managed", policy_id, policy_name)
    policies = cache_policies.get_managed_cache_policies()
    # second call should not cause an API request
    policies = cache_policies.get_managed_cache_policies()
    assert policies == {
        policy_name: policy_id,
    }
