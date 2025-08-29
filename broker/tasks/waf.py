import logging
import time
from sqlalchemy import select, and_

from broker.aws import wafv2_commercial, wafv2_govcloud
from broker.extensions import config
from broker.lib.tags import tag_key_exists
from broker.models import DedicatedALB, ModelTypes, ServiceInstanceTypes
from broker.tasks.huey import pipeline_operation

logger = logging.getLogger(__name__)


def _find_dedicated_alb_for_instance(db, service_instance) -> DedicatedALB:
    query = select(DedicatedALB).where(
        and_(
            DedicatedALB.dedicated_org == service_instance.org_id,
            DedicatedALB.alb_arn == service_instance.alb_arn,
        )
    )
    result = db.session.execute(query).first()

    if not result:
        raise RuntimeError(
            f"Could not find dedicated ALB listener for org {service_instance.org_id}"
        )

    dedicated_alb = result[0]
    return dedicated_alb


@pipeline_operation("Creating WAFv2 web ACL for ALB")
def create_alb_web_acl(operation_id, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    dedicated_alb = _find_dedicated_alb_for_instance(db, service_instance)
    create_web_acl(wafv2_govcloud, db, dedicated_alb)


@pipeline_operation("Creating custom WAFv2 web ACL")
def create_cdn_web_acl(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    create_web_acl(wafv2_commercial, db, service_instance)


@pipeline_operation("Associating custom WAFv2 web ACL to ALB")
def associate_alb_web_acl(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    dedicated_alb = _find_dedicated_alb_for_instance(db, service_instance)

    if dedicated_alb.dedicated_waf_associated:
        logger.info("WAF web ACL already associated")
        return

    associate_web_acl(
        wafv2_govcloud,
        db,
        dedicated_alb,
        dedicated_alb.dedicated_waf_web_acl_arn,
        dedicated_alb.alb_arn,
    )


def associate_web_acl(waf_client, db, instance, waf_web_acl_arn, resource_arn):
    if not waf_web_acl_arn:
        logger.info("WAF Web ACL ARN is required")
        return

    if not resource_arn:
        logger.info("Target resource ARN is required")
        return

    waf_client.associate_web_acl(
        WebACLArn=waf_web_acl_arn,
        ResourceArn=resource_arn,
    )

    instance.dedicated_waf_associated = True

    db.session.add(instance)
    db.session.commit()


@pipeline_operation("Updating WAFv2 web ACL logging configuration")
def put_alb_waf_logging_configuration(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    dedicated_alb = _find_dedicated_alb_for_instance(db, service_instance)
    put_waf_logging_configuration(
        wafv2_govcloud, dedicated_alb, config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN
    )


@pipeline_operation("Updating WAFv2 web ACL logging configuration")
def put_cdn_waf_logging_configuration(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    put_waf_logging_configuration(
        wafv2_commercial, service_instance, config.CDN_WAF_CLOUDWATCH_LOG_GROUP_ARN
    )


def put_waf_logging_configuration(waf_client, instance, log_group_arn):
    if not instance.dedicated_waf_web_acl_arn:
        logger.info("Web ACL ARN is required")
        return

    waf_client.put_logging_configuration(
        LoggingConfiguration={
            "ResourceArn": instance.dedicated_waf_web_acl_arn,
            "LogDestinationConfigs": [log_group_arn],
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

    if is_cdn_instance(instance):
        name_parts.append("cdn")
        name_parts.append(str(instance.id))
        name_parts.append("dedicated-waf")
    elif is_dedicated_alb(instance):
        name_parts.append("dedicated-org-alb")
        name_parts.append(instance.dedicated_org)
        name_parts.append("waf")

    return "-".join(name_parts)


def _get_web_acl_rules(instance, web_acl_name: str):
    if is_cdn_instance(instance):
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
    elif is_dedicated_alb(instance):
        return [
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
    if is_cdn_instance(instance):
        return "CLOUDFRONT"
    elif is_dedicated_alb(instance):
        return "REGIONAL"
    else:
        raise RuntimeError(f"unrecognized instance type: {instance.instance_type}")


def create_web_acl(waf_client, db, instance):
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

    kwargs = {}
    if instance.tags is not None:
        kwargs["Tags"] = instance.tags

    web_acl_name = generate_web_acl_name(instance, config.AWS_RESOURCE_PREFIX)

    response = waf_client.create_web_acl(
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
            response = wafv2_commercial.get_web_acl(
                Name=service_instance.dedicated_waf_web_acl_name,
                Id=service_instance.dedicated_waf_web_acl_id,
                Scope="CLOUDFRONT",
            )
            wafv2_commercial.delete_web_acl(
                Name=service_instance.dedicated_waf_web_acl_name,
                Id=service_instance.dedicated_waf_web_acl_id,
                Scope="CLOUDFRONT",
                LockToken=response["LockToken"],
            )
            notDeleted = False
        except wafv2_commercial.exceptions.WAFOptimisticLockException:
            continue
        except wafv2_commercial.exceptions.WAFNonexistentItemException:
            notDeleted = False
            return


def is_cdn_instance(instance):
    return instance.instance_type in [
        ServiceInstanceTypes.CDN_DEDICATED_WAF.value,
        ServiceInstanceTypes.DEDICATED_ALB_CDN_DEDICATED_WAF_MIGRATION.value,
    ]


def is_dedicated_alb(instance):
    return instance.instance_type == ModelTypes.DEDICATED_ALB.value
