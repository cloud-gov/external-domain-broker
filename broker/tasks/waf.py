import logging
import time

from broker.aws import wafv2
from broker.extensions import config
from broker.models import ModelTypes, ServiceInstanceTypes
from broker.tasks.huey import pipeline_operation

logger = logging.getLogger(__name__)


@pipeline_operation("Creating custom WAFv2 web ACL")
def create_web_acl(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    kwargs = {}
    if service_instance.tags is not None:
        kwargs["Tags"] = service_instance.tags
    _create_web_acl(db, service_instance, **kwargs)


@pipeline_operation("Updating WAFv2 web ACL logging configuration")
def put_logging_configuration(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if not service_instance.dedicated_waf_web_acl_arn:
        logger.info("Web ACL ARN is required")
        return

    wafv2.put_logging_configuration(
        LoggingConfiguration={
            "ResourceArn": service_instance.dedicated_waf_web_acl_arn,
            "LogDestinationConfigs": [
                config.WAF_CLOUDWATCH_LOG_GROUP_ARN,
            ],
            "LogScope": "CUSTOMER",
            "LogType": "WAF_LOGS",
        }
    )


@pipeline_operation("Deleting custom WAFv2 web ACL")
def delete_web_acl(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if (
        not service_instance.dedicated_waf_web_acl_name
        or not service_instance.dedicated_waf_web_acl_id
        or not service_instance.dedicated_waf_web_acl_arn
    ):
        logger.info("No WAF web ACL to delete")
        return

    _delete_web_acl_with_retries(operation_id, service_instance)

    service_instance.dedicated_waf_web_acl_arn = None
    service_instance.dedicated_waf_web_acl_id = None
    service_instance.dedicated_waf_web_acl_name = None

    db.session.add(service_instance)
    db.session.commit()


def generate_web_acl_name(instance, resource_prefix):
    name_parts = [resource_prefix]
    type = ""

    if instance.instance_type == ServiceInstanceTypes.CDN_DEDICATED_WAF.value:
        type = "cdn"
    elif instance.instance_type == ModelTypes.DEDICATED_ALB.value:
        type = "alb"

    if type:
        name_parts.append(type)

    name_parts = name_parts + [str(instance.id), "dedicated-waf"]
    return "-".join(name_parts)


def _get_web_acl_rules(instance, web_acl_name: str):
    if instance.instance_type == ServiceInstanceTypes.CDN_DEDICATED_WAF.value:
        return [
            {
                "Name": "RateLimit",
                "Priority": 1000,
                "Statement": {
                    "RuleGroupReferenceStatement": {
                        "ARN": config.WAF_RATE_LIMIT_RULE_GROUP_ARN
                    },
                },
                "OverrideAction": {"None": {}},
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": f"{web_acl_name}-rate-limit-rule-group",
                },
            }
        ]
    elif instance.instance_type == ModelTypes.DEDICATED_ALB.value:
        return [
            {
                "Name": "AWS-AWSManagedRulesAntiDDoSRuleSet",
                "Priority": 0,
                "Statement": {
                    "ManagedRuleGroupStatement": {
                        "VendorName": "AWS",
                        "Name": "AWSManagedRulesAntiDDoSRuleSet",
                        "ManagedRuleGroupConfigs": [
                            {
                                "AWSManagedRulesAntiDDoSRuleSet": {
                                    "ClientSideActionConfig": {
                                        "Challenge": {
                                            "UsageOfAction": "ENABLED",
                                            "Sensitivity": "HIGH",
                                            "ExemptUriRegularExpressions": [
                                                {
                                                    "RegexString": "\\/api\\/|\\.(acc|avi|css|gif|ico|jpe?g|js|json|mp[34]|ogg|otf|pdf|png|tiff?|ttf|webm|webp|woff2?|xml)$"
                                                }
                                            ],
                                        }
                                    },
                                    "SensitivityToBlock": "LOW",
                                }
                            }
                        ],
                    }
                },
                "OverrideAction": {"None": {}},
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": f"{web_acl_name}-AWS-AWSManagedRulesAntiDDoSRuleSet",
                },
            },
            {
                "Name": "AWSManagedRule-CoreRuleSet",
                "Priority": 0,
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
                    "MetricName": f"{web_acl_name}-AWS-AWSManagedRulesCommonRuleSet",
                },
            },
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
                    "MetricName": f"{web_acl_name}-AWS-AWSManagedRulesAnonymousIpList",
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
                    "MetricName": f"{web_acl_name}-AWS-ManagedRulesAmazonIpReputationList",
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
                    "MetricName": f"{web_acl_name}-AWS-KnownBadInputsRuleSet",
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
                    "MetricName": f"{web_acl_name}-AWS-AWSManagedRulesCommonRuleSet",
                },
            },
        ]
    else:
        raise RuntimeError(f"unrecognized instance type: {instance.instance_type}")


def _get_web_acl_scope(instance):
    if instance.instance_type == ServiceInstanceTypes.CDN_DEDICATED_WAF.value:
        return "CLOUDFRONT"
    elif instance.instance_type == ModelTypes.DEDICATED_ALB.value:
        return "REGIONAL"
    else:
        raise RuntimeError(f"unrecognized instance type: {instance.instance_type}")


def _create_web_acl(db, instance, **kwargs):
    if (
        instance.dedicated_waf_web_acl_arn
        and instance.dedicated_waf_web_acl_id
        and instance.dedicated_waf_web_acl_name
    ):
        logger.info(
            "Web ACL already exists",
            extra={
                "web_acl_name": instance.dedicated_waf_web_acl_name,
            },
        )
        return

    web_acl_name = generate_web_acl_name(instance, config.AWS_RESOURCE_PREFIX)

    response = wafv2.create_web_acl(
        Name=web_acl_name,
        Scope=_get_web_acl_scope(instance),
        DefaultAction={"Allow": {}},
        Rules=_get_web_acl_rules(instance, web_acl_name),
        VisibilityConfig={
            "SampledRequestsEnabled": True,
            "CloudWatchMetricsEnabled": True,
            "MetricName": web_acl_name,
        },
        **kwargs,
    )

    instance.dedicated_waf_web_acl_arn = response["Summary"]["ARN"]
    instance.dedicated_waf_web_acl_id = response["Summary"]["Id"]
    instance.dedicated_waf_web_acl_name = response["Summary"]["Name"]
    db.session.add(instance)
    db.session.commit()


def _delete_web_acl_with_retries(operation_id, service_instance):
    notDeleted = True
    num_times = 0

    while notDeleted:
        num_times += 1
        if num_times > 10:
            logger.info(
                "Failed to delete web ACL",
                extra={
                    "operation_id": operation_id,
                    "web_acl_name": service_instance.dedicated_waf_web_acl_name,
                },
            )
            raise RuntimeError("Failed to delete WAFv2 web ACL")
        time.sleep(config.DELETE_WEB_ACL_WAIT_RETRY_TIME)
        try:
            response = wafv2.get_web_acl(
                Name=service_instance.dedicated_waf_web_acl_name,
                Id=service_instance.dedicated_waf_web_acl_id,
                Scope="CLOUDFRONT",
            )
            wafv2.delete_web_acl(
                Name=service_instance.dedicated_waf_web_acl_name,
                Id=service_instance.dedicated_waf_web_acl_id,
                Scope="CLOUDFRONT",
                LockToken=response["LockToken"],
            )
            notDeleted = False
        except wafv2.exceptions.WAFOptimisticLockException:
            continue
        except wafv2.exceptions.WAFNonexistentItemException:
            notDeleted = False
            return
