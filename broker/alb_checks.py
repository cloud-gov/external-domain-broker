import logging

from sqlalchemy import func, select, desc

from broker.extensions import db
from broker.models import ALBServiceInstance, Certificate

logger = logging.getLogger(__name__)

def find_duplicate_alb_certs():
    query = select(
        ALBServiceInstance.id,
        func.count(Certificate.id).label("cert_count")
    ).select_from(Certificate).join(
        ALBServiceInstance,
        ALBServiceInstance.id == Certificate.service_instance_id,
    ).where(
        ALBServiceInstance.current_certificate_id != Certificate.id
    ).group_by(
        ALBServiceInstance.id
    ).having(
        func.count(Certificate.id) > 0
    ).order_by(
        desc("cert_count")
    )
    return db.engine.execute(query).fetchall()

def print_duplicate_alb_cert_metrics(file):
  for duplicate_result in find_duplicate_alb_certs():
    [service_instance_id, num_duplicates] = duplicate_result
    logger.info(f"service_instance_cert_count{{service_instance_id=\"{service_instance_id}\"}} {num_duplicates}")
    if file is not None:
        print(
            f"service_instance_cert_count{{service_instance_id=\"{service_instance_id}\"}} {num_duplicates}",
            file=file
        )
