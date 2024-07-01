import pytest

from broker.aws import wafv2 as real_wafv2
from tests.lib.fake_aws import FakeAWS


class FakeWAFV2(FakeAWS):
    def expect_create_web_acl(self, id: str, rule_group_arn: str):
        method = "create_web_acl"
        waf_name = f"{id}-dedicated-waf"
        request = {
            "Name": waf_name,
            "Scope": "CLOUDFRONT",
            "DefaultAction": {"Allow": {}},
            "Rules": [
                {
                    "Name": "RateLimit",
                    "Priority": 1000,
                    "Statement": {
                        "RuleGroupReferenceStatement": {"ARN": rule_group_arn},
                    },
                    "VisibilityConfig": {
                        "SampledRequestsEnabled": True,
                        "CloudWatchMetricsEnabled": True,
                        "MetricName": f"{id}-rate-limit-rule-group",
                    },
                }
            ],
            "VisibilityConfig": {
                "SampledRequestsEnabled": True,
                "CloudWatchMetricsEnabled": True,
                "MetricName": waf_name,
            },
        }
        response = {
            "Summary": {
                "Id": f"{waf_name}-id",
                "Name": waf_name,
                "ARN": f"arn:aws:wafv2::000000000000:global/webacl/{waf_name}",
            }
        }
        self.stubber.add_response(method, response, request)

    def expect_get_web_acl(self, id: str, name: str):
        self.stubber.add_response(
            "get_web_acl",
            {
                "LockToken": "fake-token",
            },
            {
                "Name": name,
                "Id": id,
                "Scope": "CLOUDFRONT",
            },
        )

    def expect_delete_web_acl(self, id: str, name: str):
        self.stubber.add_response(
            "delete_web_acl",
            {},
            {"Name": name, "Id": id, "Scope": "CLOUDFRONT", "LockToken": "fake-token"},
        )


@pytest.fixture(autouse=True)
def wafv2():
    with FakeWAFV2.stubbing(real_wafv2) as wafv2_stubber:
        yield wafv2_stubber
