from broker.extensions import config


class CachePolicyManager:
    def __init__(self, cloudfront):
        self.policies = {}
        self.cloudfront = cloudfront

    def get_managed_cache_policies(self) -> dict[str, str]:
        policy_type = "managed"
        if policy_type not in self.policies:
            self._list_cache_policies(policy_type)
        return self.policies[policy_type]

    def _list_cache_policies(self, policy_type):
        # TODO: do we need to handle paging?
        response = self.cloudfront.list_cache_policies(Type=policy_type)
        policies = {}
        for item in response["CachePolicyList"]["Items"]:
            if "CachePolicy" not in item:
                continue

            policy = item["CachePolicy"]
            policy_name = policy["CachePolicyConfig"]["Name"]
            if policy_name not in config.ALLOWED_AWS_MANAGED_CACHE_POLICIES:
                continue

            policies[policy_name] = policy["Id"]
        self.policies[policy_type] = policies
