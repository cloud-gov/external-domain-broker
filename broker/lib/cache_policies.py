class CachePolicies:
    def __init__(self, cloudfront):
        self.policies = {}
        self.cloudfront = cloudfront

    def get_managed_cache_policies(self):
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
            policies[policy["CachePolicyConfig"]["Name"]] = policy["Id"]
        self.policies[policy_type] = policies
