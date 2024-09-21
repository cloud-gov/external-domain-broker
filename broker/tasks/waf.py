import logging
import time

from broker.aws import wafv2
from broker.extensions import config
from broker.tasks.huey import pipeline_operation

logger = logging.getLogger(__name__)


@pipeline_operation("Creating custom WAFv2 web ACL")
def create_web_acl(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if (
        service_instance.dedicated_waf_web_acl_arn
        and service_instance.dedicated_waf_web_acl_id
        and service_instance.dedicated_waf_web_acl_name
    ):
        logger.info(
            "Web ACL already exists",
            extra={
                "web_acl_name": service_instance.dedicated_waf_web_acl_name,
            },
        )
        return

    web_acl_name = generate_web_acl_name(service_instance)

    kwargs = {}
    if service_instance.tags is not None:
        kwargs["Tags"] = service_instance.tags

    response = wafv2.create_web_acl(
        Name=web_acl_name,
        Scope="CLOUDFRONT",
        DefaultAction={"Allow": {}},
        Rules=[
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
        ],
        VisibilityConfig={
            "SampledRequestsEnabled": True,
            "CloudWatchMetricsEnabled": True,
            "MetricName": web_acl_name,
        },
        **kwargs,
    )

    service_instance.dedicated_waf_web_acl_arn = response["Summary"]["ARN"]
    service_instance.dedicated_waf_web_acl_id = response["Summary"]["Id"]
    service_instance.dedicated_waf_web_acl_name = response["Summary"]["Name"]
    db.session.add(service_instance)
    db.session.commit()


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


def generate_web_acl_name(service_instance):
    return f"{config.AWS_RESOURCE_PREFIX}-{service_instance.id}-dedicated-waf"


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
