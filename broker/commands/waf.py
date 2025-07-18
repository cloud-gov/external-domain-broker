import logging
import time

from broker.aws import wafv2_govcloud
from broker.extensions import config, db
from broker.models import DedicatedALB
from broker.tasks.waf import (
    create_web_acl,
    put_waf_logging_configuration,
    associate_web_acl,
)


logger = logging.getLogger(__name__)


def wait_for_web_acl_to_exist(waf_web_acl_arn):
    web_acl_exists = False
    num_times = 0

    while not web_acl_exists:
        num_times += 1
        if num_times > config.AWS_POLL_MAX_ATTEMPTS:
            raise RuntimeError(
                f"Reached maximum attempts {config.AWS_POLL_MAX_ATTEMPTS} waiting for web ACL to exist"
            )

        time.sleep(config.AWS_POLL_WAIT_TIME_IN_SECONDS)
        try:
            wafv2_govcloud.get_web_acl(ARN=waf_web_acl_arn)
            web_acl_exists = True
        except wafv2_govcloud.exceptions.WAFNonexistentItemException:
            continue


def add_dedicated_alb_waf_web_acls():
    dedicated_albs = DedicatedALB.query.all()

    for dedicated_alb in dedicated_albs:
        if (
            dedicated_alb.dedicated_waf_web_acl_arn
            and dedicated_alb.dedicated_waf_web_acl_id
            and dedicated_alb.dedicated_waf_web_acl_name
            and dedicated_alb.dedicated_waf_associated
        ):
            continue

        create_web_acl(wafv2_govcloud, db, dedicated_alb)
        wait_for_web_acl_to_exist(dedicated_alb.dedicated_waf_web_acl_arn)
        put_waf_logging_configuration(
            wafv2_govcloud, dedicated_alb, config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN
        )
        associate_web_acl(
            wafv2_govcloud,
            db,
            dedicated_alb,
            dedicated_alb.dedicated_waf_web_acl_arn,
            dedicated_alb.alb_arn,
        )
