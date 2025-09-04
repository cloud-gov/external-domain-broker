import pytest

from broker.aws import wafv2_commercial as real_wafv2_c, wafv2_govcloud as real_wafv2_g
from broker.lib.tags import Tag
from broker.extensions import config
from tests.lib.fake_aws import FakeAWS


class FakeWAFV2(FakeAWS):
    def expect_cdn_create_web_acl(self, id: str, rule_group_arn: str, tags: list[Tag]):
        method = "create_web_acl"
        waf_name = f"{config.AWS_RESOURCE_PREFIX}-cdn-{id}-dedicated-waf"

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
                    "OverrideAction": {"None": {}},
                    "VisibilityConfig": {
                        "SampledRequestsEnabled": True,
                        "CloudWatchMetricsEnabled": True,
                        "MetricName": f"{waf_name}-rate-limit-rule-group",
                    },
                }
            ],
            "VisibilityConfig": {
                "SampledRequestsEnabled": True,
                "CloudWatchMetricsEnabled": True,
                "MetricName": waf_name,
            },
        }

        if tags:
            request["Tags"] = tags

        response = {
            "Summary": {
                "Id": generate_fake_waf_web_acl_id(waf_name),
                "Name": waf_name,
                "ARN": generate_fake_waf_web_acl_arn(waf_name),
            }
        }
        self.stubber.add_response(method, response, request)

    def expect_alb_create_web_acl(self, org_id: str, tags: list[Tag]):
        method = "create_web_acl"
        waf_name = f"{config.AWS_RESOURCE_PREFIX}-dedicated-org-alb-{org_id}-waf"

        request = {
            "Name": waf_name,
            "Scope": "REGIONAL",
            "DefaultAction": {"Allow": {}},
            "Rules": [
                {
                    "Name": "AWS-AWSManagedRulesAnonymousIpList",
                    "Priority": 10,
                    "Statement": {
                        "ManagedRuleGroupStatement": {
                            "VendorName": "AWS",
                            "Name": "AWSManagedRulesAnonymousIpList",
                        }
                    },
                    "OverrideAction": {"None": {}},
                    "VisibilityConfig": {
                        "SampledRequestsEnabled": True,
                        "CloudWatchMetricsEnabled": True,
                        "MetricName": f"{waf_name}-AWS-AWSManagedRulesAnonymousIpList",
                    },
                },
                {
                    "Name": "AWS-AWSManagedRulesAmazonIpReputationList",
                    "Priority": 20,
                    "Statement": {
                        "ManagedRuleGroupStatement": {
                            "VendorName": "AWS",
                            "Name": "AWSManagedRulesAmazonIpReputationList",
                        }
                    },
                    "OverrideAction": {"None": {}},
                    "VisibilityConfig": {
                        "SampledRequestsEnabled": True,
                        "CloudWatchMetricsEnabled": True,
                        "MetricName": f"{waf_name}-AWS-ManagedRulesAmazonIpReputationList",
                    },
                },
                {
                    "Name": "AWS-KnownBadInputsRuleSet",
                    "Priority": 30,
                    "Statement": {
                        "ManagedRuleGroupStatement": {
                            "VendorName": "AWS",
                            "Name": "AWSManagedRulesKnownBadInputsRuleSet",
                        }
                    },
                    "OverrideAction": {"None": {}},
                    "VisibilityConfig": {
                        "SampledRequestsEnabled": True,
                        "CloudWatchMetricsEnabled": True,
                        "MetricName": f"{waf_name}-AWS-KnownBadInputsRuleSet",
                    },
                },
                {
                    "Name": "AWSManagedRule-CoreRuleSet",
                    "Priority": 40,
                    "Statement": {
                        "ManagedRuleGroupStatement": {
                            "VendorName": "AWS",
                            "Name": "AWSManagedRulesCommonRuleSet",
                        }
                    },
                    "OverrideAction": {"None": {}},
                    "VisibilityConfig": {
                        "SampledRequestsEnabled": True,
                        "CloudWatchMetricsEnabled": True,
                        "MetricName": f"{waf_name}-AWS-AWSManagedRulesCommonRuleSet",
                    },
                },
            ],
            "VisibilityConfig": {
                "SampledRequestsEnabled": True,
                "CloudWatchMetricsEnabled": True,
                "MetricName": waf_name,
            },
        }

        if tags:
            request["Tags"] = tags

        response = {
            "Summary": {
                "Id": generate_fake_waf_web_acl_id(waf_name),
                "Name": waf_name,
                "ARN": generate_fake_waf_web_acl_arn(waf_name),
            }
        }
        self.stubber.add_response(method, response, request)

    def expect_alb_associate_web_acl(self, waf_arn: str, alb_arn: str):
        method = "associate_web_acl"

        request = {
            "WebACLArn": waf_arn,
            "ResourceArn": alb_arn,
        }

        self.stubber.add_response(method, {}, request)

    def expect_get_web_acl(
        self, id: str = "", name: str = "", arn: str = "", scope: str = ""
    ):
        params = {}
        if id:
            params["Id"] = id

        if name:
            params["Name"] = name

        if arn:
            params["ARN"] = arn

        if scope:
            params["Scope"] = scope

        self.stubber.add_response(
            "get_web_acl",
            {
                "LockToken": "fake-token",
            },
            params,
        )

    def expect_get_web_acl_not_found(
        self, id: str = "", name: str = "", arn: str = "", scope: str = ""
    ):
        params = {}
        if id:
            params["Id"] = id

        if name:
            params["Name"] = name

        if arn:
            params["ARN"] = arn

        if scope:
            params["Scope"] = scope

        self.stubber.add_client_error(
            "get_web_acl",
            service_error_code="WAFNonexistentItemException",
            service_message="Not found",
            http_status_code=404,
            expected_params=params,
        )

    def expect_delete_web_acl_lock_exception(self, id: str, name: str):
        self.stubber.add_client_error(
            "delete_web_acl",
            service_error_code="WAFOptimisticLockException",
            service_message="Lock issue",
            http_status_code=500,
            expected_params={
                "Name": name,
                "Id": id,
                "Scope": "CLOUDFRONT",
                "LockToken": "fake-token",
            },
        )

    def expect_delete_web_acl(self, id: str, name: str):
        self.stubber.add_response(
            "delete_web_acl",
            {},
            {"Name": name, "Id": id, "Scope": "CLOUDFRONT", "LockToken": "fake-token"},
        )

    def expect_put_logging_configuration(self, resource_arn: str, log_group_arn: str):
        method = "put_logging_configuration"

        request = {
            "LoggingConfiguration": {
                "ResourceArn": resource_arn,
                "LogDestinationConfigs": [
                    log_group_arn,
                ],
                "LogScope": "CUSTOMER",
                "LogType": "WAF_LOGS",
            }
        }

        response = {}
        self.stubber.add_response(method, response, request)

    def expect_tag_resource(self, resource_arn: str, tags: list[Tag]):
        method = "tag_resource"

        request = {
            "ResourceARN": resource_arn,
            "Tags": tags,
        }

        response = {}
        self.stubber.add_response(method, response, request)


def generate_fake_waf_web_acl_arn(waf_name):
    return f"arn:aws:wafv2::000000000000:global/webacl/{waf_name}"


def generate_fake_waf_web_acl_id(waf_name):
    return f"{waf_name}-id"


@pytest.fixture(autouse=True)
def wafv2_commercial():
    with FakeWAFV2.stubbing(real_wafv2_c) as wafv2_stubber:
        yield wafv2_stubber


@pytest.fixture(autouse=True)
def wafv2_govcloud():
    with FakeWAFV2.stubbing(real_wafv2_g) as wafv2_stubber:
        yield wafv2_stubber
