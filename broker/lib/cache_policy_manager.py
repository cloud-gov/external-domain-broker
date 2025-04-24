from broker.extensions import config


class CachePolicyManager:
    def __init__(self, cloudfront):
        self._managed_policies = None
        self.cloudfront = cloudfront

    def get_managed_policy_id(self, policy) -> str:
        return self.managed_policies[policy]

    @property
    def managed_policies(self) -> dict[str, str]:
        if self._managed_policies is None:
            self._managed_policies = self._list_cache_policies("managed")
        return self._managed_policies

    def _list_cache_policies(self, policy_type) -> dict[str, str]:
        response = self.cloudfront.list_cache_policies(Type=policy_type)
        cache_policy_list = response.get("CachePolicyList", {})
        cache_policies = cache_policy_list.get("Items", [])
        while "NextMarker" in cache_policy_list:
            response = self.cloudfront.list_cache_policies(
                Type=policy_type, Marker=response["NextMarker"]
            )
            cache_policy_list = response.get("CachePolicyList", {})
            cache_policies.extend(cache_policy_list.get("Items", []))

        cache_policies_map = {}
        for item in cache_policies:
            if "CachePolicy" not in item:
                continue

            policy = item["CachePolicy"]
            policy_name = policy["CachePolicyConfig"]["Name"]
            if policy_name not in config.ALLOWED_AWS_MANAGED_CACHE_POLICIES:
                continue

            cache_policies_map[policy_name] = policy["Id"]
        return cache_policies_map
