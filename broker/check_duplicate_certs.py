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

def get_duplicate_certs_for_service(service_instance_id):
    return Certificate.query.join(
        ALBServiceInstance,
        ALBServiceInstance.id == Certificate.service_instance_id,
    ).filter(
        Certificate.service_instance_id == service_instance_id,
        Certificate.id != ALBServiceInstance.current_certificate_id
    ).where(
        ALBServiceInstance.current_certificate_id != Certificate.id
    ).all()

def log_duplicate_alb_cert_metrics(logger=logger):
  for duplicate_result in find_duplicate_alb_certs():
    [service_instance_id, num_duplicates] = duplicate_result
    logger.info(f"service_instance_cert_count{{service_instance_id=\"{service_instance_id}\"}} {num_duplicates}")

def fix_duplicate_alb_certs():
  for duplicate_result in find_duplicate_alb_certs():
    [service_instance_id, num_duplicates] = duplicate_result
    duplicate_certs = get_duplicate_certs_for_service(service_instance_id)
    logger.info(f"Found {num_duplicates} duplicate certificates for service instance {service_instance_id}")
    return duplicate_certs
    
