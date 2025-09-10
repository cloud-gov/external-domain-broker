import logging
import time

from broker.aws import wafv2_govcloud
from broker.extensions import config, db
from broker.models import DedicatedALB
from broker.tasks.waf import (
    create_web_acl,
    put_waf_logging_configuration,
    associate_web_acl,
    _delete_web_acl_with_retries,
    _get_web_acl_scope,
    generate_web_acl_name,
)

from types_boto3_wafv2 import WAFV2Client


logger = logging.getLogger(__name__)


def wait_for_web_acl_to_exist(
    waf_client: WAFV2Client, waf_web_acl_arn, retry_maximum_attempts, retry_delay_time
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


def update_dedicated_alb_with_web_acl_info(waf_client: WAFV2Client, dedicated_alb):
    response = waf_client.list_web_acls(Scope="REGIONAL")
    waf_web_acl_name = generate_web_acl_name(dedicated_alb, config.AWS_RESOURCE_PREFIX)
    filtered_web_acls = [
        web_acl
        for web_acl in response["WebACLs"]
        if web_acl.get("Name") == waf_web_acl_name
    ]

    if len(filtered_web_acls) == 0:
        raise RuntimeError("Could not find web ACL")

    web_acl = filtered_web_acls[0]
    if "ARN" not in web_acl:
        raise RuntimeError("Could not get ARN from web ACL")

    if "Id" not in web_acl:
        raise RuntimeError("Could not get ID from web ACL")

    if "Name" not in web_acl:
        raise RuntimeError("Could not get name from web ACL")

    dedicated_alb.dedicated_waf_web_acl_arn = web_acl["ARN"]
    dedicated_alb.dedicated_waf_web_acl_id = web_acl["Id"]
    dedicated_alb.dedicated_waf_web_acl_name = web_acl["Name"]
    db.session.add(dedicated_alb)
    db.session.commit()


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

        already_exists = create_web_acl(
            wafv2_govcloud, db, dedicated_alb, force_create_new
        )
        # If the web ACL for this dedicated ALB had previously been created, it is not created
        # again, so we need to manually update the dedicated ALB record with the web ACL info
        if already_exists:
            update_dedicated_alb_with_web_acl_info(wafv2_govcloud, dedicated_alb)
        else:
            wait_for_web_acl_to_exist(
                wafv2_govcloud,
                dedicated_alb.dedicated_waf_web_acl_arn,
                config.AWS_POLL_MAX_ATTEMPTS,
                config.AWS_POLL_WAIT_TIME_IN_SECONDS,
            )
        put_waf_logging_configuration(
            wafv2_govcloud, dedicated_alb, config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN
        )


def update_dedicated_alb_waf_web_acls():
    dedicated_albs = DedicatedALB.query.all()

    for dedicated_alb in dedicated_albs:
        if (
            not dedicated_alb.dedicated_waf_web_acl_arn
            or not dedicated_alb.dedicated_waf_web_acl_id
            or not dedicated_alb.dedicated_waf_web_acl_name
        ):
            continue

        associated_web_acl_info = get_associated_waf_web_acl_info(dedicated_alb.alb_arn)
        associated_web_acl_arn = get_associated_waf_web_acl_arn(associated_web_acl_info)

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

        wait_for_associated_waf_web_acl_arn(
            dedicated_alb.alb_arn, dedicated_alb.dedicated_waf_web_acl_arn
        )

        _delete_web_acl_with_retries(
            wafv2_govcloud,
            get_associated_waf_web_acl_name(associated_web_acl_info),
            get_associated_waf_web_acl_id(associated_web_acl_info),
            _get_web_acl_scope(dedicated_alb),
            {},
        )


def wait_for_associated_waf_web_acl_arn(resource_arn, expected_waf_web_acl_arn):
    isAssociated = False
    num_times = 0

    while not isAssociated:
        num_times += 1
        if num_times > config.AWS_POLL_MAX_ATTEMPTS:
            logger.info(
                "Failed to confirm web ACL association",
                extra={
                    "resource_arn": resource_arn,
                },
            )
            raise RuntimeError(
                f"Failed to confirm association of web ACL for {resource_arn}"
            )
        time.sleep(config.AWS_POLL_WAIT_TIME_IN_SECONDS)
        associated_waf_web_acl_arn = get_associated_waf_web_acl_arn(
            get_associated_waf_web_acl_info(resource_arn)
        )
        isAssociated = associated_waf_web_acl_arn == expected_waf_web_acl_arn


def get_associated_waf_web_acl_arn(web_acl_info):
    return web_acl_info["ARN"]


def get_associated_waf_web_acl_id(web_acl_info):
    return web_acl_info["Id"]


def get_associated_waf_web_acl_name(web_acl_info):
    return web_acl_info["Name"]


def get_associated_waf_web_acl_info(resource_arn):
    response = wafv2_govcloud.get_web_acl_for_resource(ResourceArn=resource_arn)
    return response["WebACL"]
