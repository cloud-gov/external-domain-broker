import uuid

from broker.aws import cloudfront as cloudfront_svc
from broker.lib.cache_policies import CachePolicies


def test_get_managed_cache_policies_returns_saved_results(cloudfront):
    policy_id = str(uuid.uuid4())
    policy_name = "fake-policy"

    cache_policies = CachePolicies(cloudfront_svc)
    cache_policies.policies = {
        "managed": {
            policy_name: policy_id,
        }
    }
    policies = cache_policies.get_managed_cache_policies()
    assert policies == {
        policy_name: policy_id,
    }
