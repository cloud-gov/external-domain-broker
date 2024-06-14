import logging

from sqlalchemy.orm.attributes import flag_modified

from broker.aws import wafv2
from broker.extensions import config, db
from broker.models import Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.retriable_task
def create_web_acl(operation_id: str, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Creating custom WAFv2 web ACL"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    waf_name = f"{service_instance.cloudfront_distribution_id}-dedicated-waf"
    response = wafv2.create_web_acl(
        Name=waf_name,
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
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": f"{service_instance.cloudfront_distribution_id}-rate-limit-rule-group",
                },
            }
        ],
        VisibilityConfig={
            "SampledRequestsEnabled": True,
            "CloudWatchMetricsEnabled": True,
            "MetricName": waf_name,
        },
    )

    service_instance.dedicated_waf_web_acl_arn = response["Summary"]["ARN"]
    db.session.add(service_instance)
    db.session.commit()
