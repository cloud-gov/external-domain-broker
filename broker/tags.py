import logging

from sqlalchemy import select

from broker.extensions import db
from broker.models import ServiceInstance

logger = logging.getLogger(__name__)


# TODO: implement ability to find instances without tags and update them
def find_instances_without_tags():
    query = (
        select(ServiceInstance.id)
        .select_from(ServiceInstance)
        .where(ServiceInstance.tags == None)
    )
    return db.session.execute(query).fetchall()
