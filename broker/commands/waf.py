from broker.aws import wafv2_govcloud
from broker.extensions import config, db
from broker.models import DedicatedALB
from broker.tasks.waf import create_web_acl, put_waf_logging_configuration


def add_dedicated_alb_waf_web_acls():
    dedicated_albs = DedicatedALB.query.all()

    for dedicated_alb in dedicated_albs:
        if (
            dedicated_alb.dedicated_waf_web_acl_arn
            and dedicated_alb.dedicated_waf_web_acl_id
            and dedicated_alb.dedicated_waf_web_acl_name
        ):
            continue

        create_web_acl(wafv2_govcloud, db, dedicated_alb)
        put_waf_logging_configuration(
            wafv2_govcloud, dedicated_alb, config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN
        )
