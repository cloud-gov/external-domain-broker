import logging

from sqlalchemy import func, select, desc

from broker.aws import alb
from broker.extensions import config, db
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

def delete_duplicate_cert_db_record(duplicate_cert):
    Certificate.query.filter(
        Certificate.id == duplicate_cert.id
    ).delete()

def get_matching_alb_listener_arns_for_cert_arns(duplicate_cert_arns, listener_arns=config.ALB_LISTENER_ARNS, alb=alb):
    matched_listeners_dict = {}
    all_matched_cert_arns = []
    for listener_arn in listener_arns:
        response = alb.describe_listener_certificates(
            ListenerArn=listener_arn,
        )
        listener_cert_arns = [cert["CertificateArn"] for cert in response["Certificates"]]
        # Get list of duplicate cert ARNs that were matched for this ALB listener ARN
        matched_cert_arns = list(set(listener_cert_arns) & set(duplicate_cert_arns))

        if len(matched_cert_arns) > 0:
            # Update dict of cert ARNs to ALB listener ARNs
            matched_listeners_dict.update(dict(zip(matched_cert_arns, [listener_arn] * len(matched_cert_arns))))
            all_matched_cert_arns = all_matched_cert_arns + matched_cert_arns
            # We have matched all the duplicate cert ARNs, so break out of loop
            if len(all_matched_cert_arns) == len(duplicate_cert_arns):
                break
    return matched_listeners_dict

def fix_duplicate_alb_certs():
  for duplicate_result in find_duplicate_alb_certs():
    [service_instance_id, num_duplicates] = duplicate_result
    duplicate_certs = get_duplicate_certs_for_service(service_instance_id)
    logger.info(f"Found {num_duplicates} duplicate certificates for service instance {service_instance_id}")
    duplicate_cert_arns = [cert.iam_server_certificate_arn for cert in duplicate_certs]
    for duplicate_cert in duplicate_certs:
        delete_duplicate_cert_db_record(duplicate_cert)
    
