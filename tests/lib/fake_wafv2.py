import pytest

from broker.aws import wafv2 as real_wafv2
from tests.lib.fake_aws import FakeAWS


class FakeWAFV2(FakeAWS):
    def expect_create_web_acl(self, distribution_id: str, rule_group_arn: str):
        method = "create_web_acl"
        waf_name = f"{distribution_id}-dedicated-waf"
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
                        "MetricName": f"{distribution_id}-rate-limit-rule-group",
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
                "ARN": f"arn:aws:wafv2::000000000000:global/webacl/{waf_name}",
            }
        }
        self.stubber.add_response(method, response, request)


@pytest.fixture(autouse=True)
def wafv2():
    with FakeWAFV2.stubbing(real_wafv2) as wafv2_stubber:
        yield wafv2_stubber
