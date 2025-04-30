from broker.extensions import config


class OriginRequestPolicyManager:
    def __init__(self, cloudfront):
        self._managed_policies = None
        self.cloudfront = cloudfront

    def get_managed_policy_id(self, policy) -> str:
        return self.managed_policies[policy]

    @property
    def managed_policies(self) -> dict[str, str]:
        if self._managed_policies is None:
            self._managed_policies = self._list_origin_request_policies("managed")
        return self._managed_policies

    def _list_origin_request_policies(self, policy_type):
        origin_request_policies = []

        response = self.cloudfront.list_origin_request_policies(Type=policy_type)
        origin_request_policies.extend(
            response.get("OriginRequestPolicyList", {}).get("Items", [])
        )
        while "NextMarker" in response.get("OriginRequestPolicyList", {}):
            response = self.cloudfront.list_origin_request_policies(
                Type=policy_type,
                Marker=response["OriginRequestPolicyList"]["NextMarker"],
            )
            origin_request_policies.extend(
                response.get("OriginRequestPolicyList", {}).get("Items", [])
            )

        origin_request_policies_map = {}
        for item in origin_request_policies:
            if "OriginRequestPolicy" not in item:
                continue

            policy = item["OriginRequestPolicy"]
            policy_name = policy["OriginRequestPolicyConfig"]["Name"]
            if (
                policy_name
                not in config.ALLOWED_AWS_MANAGED_ORIGIN_VIEWER_REQUEST_POLICIES
            ):
                continue

            origin_request_policies_map[policy_name] = policy["Id"]
        return origin_request_policies_map
