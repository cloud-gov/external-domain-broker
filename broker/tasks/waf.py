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

    # TODO: not sure how errors should be handled here?
    response = wafv2.create_web_acl(
        Name=f"{service_instance.cloudfront_distribution_id}-dedicated-waf",
        Scope="CLOUDFRONT",
        Rules=[
            {
                "Statement": {
                    "RuleGroupReferenceStatement": {
                        "ARN": config.WAF_RATE_LIMIT_RULE_GROUP_ARN
                    }
                }
            }
        ],
    )

    service_instance.dedicated_waf_web_acl_arn = response["Summary"]["ARN"]
    db.session.add(service_instance)
    db.session.commit()
