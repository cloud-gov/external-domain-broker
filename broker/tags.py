import logging

from sqlalchemy import func, select, desc

from broker.aws import alb, iam_govcloud
from broker.extensions import config, db
from broker.models import ServiceInstance, CDNServiceInstance

logger = logging.getLogger(__name__)


def find_cdn_instances_without_tags():
    query = (
        select(CDNServiceInstance.cloudfront_distribution_arn)
        .select_from(CDNServiceInstance)
        .where(CDNServiceInstance.tags == None)
    )
    return db.session.execute(query).fetchall()
