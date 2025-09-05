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


def wait_for_web_acl_to_exist(
    waf_client, waf_web_acl_arn, retry_maximum_attempts, retry_delay_time
):
    web_acl_exists = False
    num_times = 0

    while not web_acl_exists:
        num_times += 1
        if num_times > retry_maximum_attempts:
            raise RuntimeError(
                f"Reached maximum attempts {retry_maximum_attempts} waiting for web ACL to exist"
            )

        time.sleep(retry_delay_time)
        try:
            waf_client.get_web_acl(ARN=waf_web_acl_arn)
            web_acl_exists = True
        except wafv2_govcloud.exceptions.WAFNonexistentItemException:
            continue


def create_dedicated_alb_waf_web_acls(force_create_new=False):
    dedicated_albs = DedicatedALB.query.all()

    for dedicated_alb in dedicated_albs:
        if (
            not force_create_new
            and dedicated_alb.dedicated_waf_web_acl_arn
            and dedicated_alb.dedicated_waf_web_acl_id
            and dedicated_alb.dedicated_waf_web_acl_name
            and dedicated_alb.dedicated_waf_associated
        ):
            continue

        create_web_acl(wafv2_govcloud, db, dedicated_alb, force_create_new)
        wait_for_web_acl_to_exist(
            wafv2_govcloud,
            dedicated_alb.dedicated_waf_web_acl_arn,
            config.AWS_POLL_MAX_ATTEMPTS,
            config.AWS_POLL_WAIT_TIME_IN_SECONDS,
        )
        put_waf_logging_configuration(
            wafv2_govcloud, dedicated_alb, config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN
        )


def associate_dedicated_alb_waf_web_acls():
    dedicated_albs = DedicatedALB.query.all()

    for dedicated_alb in dedicated_albs:
        if (
            not dedicated_alb.dedicated_waf_web_acl_arn
            or not dedicated_alb.dedicated_waf_web_acl_id
            or not dedicated_alb.dedicated_waf_web_acl_name
        ):
            continue

        response = wafv2_govcloud.get_web_acl_for_resource(
            ResourceArn=dedicated_alb.alb_arn
        )
        associated_web_acl_arn = response["WebACL"]["ARN"]

        # If the WAF web ACL actually associated with the ALB already matches the
        # one we expect in the database, then return because there is no need to
        # update the associated WAF web ACL
        if (
            associated_web_acl_arn
            and associated_web_acl_arn == dedicated_alb.dedicated_waf_web_acl_arn
        ):
            logger.info("Current WAF web ACL already matches expected resource")
            return

        # Otherwise, continue and update the associated WAF web ACL. We likely
        # reach this condition because the create_dedicated_alb_waf_web_acls
        # command was run with force_new_create=True, which creates new WAF
        # web ACLs and updates the values on dedicated_alb, but does not actually
        # associate the new web ACLs with the ALB
        associate_web_acl(
            wafv2_govcloud,
            db,
            dedicated_alb,
            dedicated_alb.dedicated_waf_web_acl_arn,
            dedicated_alb.alb_arn,
        )
