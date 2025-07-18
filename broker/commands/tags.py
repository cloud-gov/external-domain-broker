import logging

from broker.aws import wafv2_govcloud
from broker.extensions import config, db
from broker.lib.tags import create_resource_tags, generate_tags
from broker.models import DedicatedALB

logger = logging.getLogger(__name__)


def add_dedicated_alb_tags():
    dedicated_albs = DedicatedALB.query.all()

    for dedicated_alb in dedicated_albs:
        if dedicated_alb.tags:
            continue

        if not dedicated_alb.dedicated_org:
            logger.info(
                "Organization ID is required to generate tags for dedicated ALB"
            )
            continue

        tags = create_resource_tags(
            generate_tags(
                config.FLASK_ENV,
                organization_guid=dedicated_alb.dedicated_org,
            )
        )

        dedicated_alb.tags = tags
        db.session.add(dedicated_alb)
        db.session.commit()

        if not dedicated_alb.dedicated_waf_web_acl_arn:
            logger.info("Web ACL ARN is required")
            continue

        wafv2_govcloud.tag_resource(
            ResourceARN=dedicated_alb.dedicated_waf_web_acl_arn,
            Tags=tags,
        )
