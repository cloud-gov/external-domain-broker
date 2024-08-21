import logging

from sqlalchemy import select

from broker.extensions import db
from broker.models import CDNServiceInstance

logger = logging.getLogger(__name__)


# TODO: implement ability to find instances without tags and update them
def find_cdn_instances_without_tags():
    query = (
        select(CDNServiceInstance.id, CDNServiceInstance.cloudfront_distribution_arn)
        .select_from(CDNServiceInstance)
        .where(CDNServiceInstance.tags == None)
    )
    return db.session.execute(query).fetchall()
