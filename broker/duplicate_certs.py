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

def delete_cert_record_and_resource(certificate, listener_arn, alb=alb, db=db):
    try:
        logger.info(f"Deleting duplicate certificate {certificate.id} for service instance {certificate.service_instance_id}")
        delete_duplicate_cert_db_record(certificate)
                    
        logger.info(f"Removing certificate {certificate.iam_server_certificate_arn} from listener {listener_arn}")
        alb.remove_listener_certificates(
            ListenerArn=listener_arn,
            Certificates=[{"CertificateArn": certificate.iam_server_certificate_arn}]
        )

        # only commit deletion if deleting certificate ARN was successful
        db.session.commit()
    except Exception:
        db.session.rollback()

def get_matching_alb_listener_arns_for_cert_arns(duplicate_cert_arns, listener_arns, alb=alb):
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

def remove_duplicate_alb_certs(listener_arns=config.get("ALB_LISTENER_ARNS", "")):
  for duplicate_result in find_duplicate_alb_certs():
    [service_instance_id, num_duplicates] = duplicate_result

    service_instance = ALBServiceInstance.query.get(service_instance_id)
    if service_instance.has_active_operations():
        logger.info(f"Instance {service_instance_id} has an active operation in progress, so duplicate certificates cannot be removed. Try again in a few minutes.")
        continue

    logger.info(f"Found {num_duplicates} duplicate certificates for service instance {service_instance_id}")
    
    duplicate_certs = get_duplicate_certs_for_service(service_instance_id)
    duplicate_cert_arns = [cert.iam_server_certificate_arn for cert in duplicate_certs]
    
    # Get dictionary for reverse lookup of listener ARN by certificate ARN
    listener_arns_dict = get_matching_alb_listener_arns_for_cert_arns(duplicate_cert_arns, listener_arns)

    for duplicate_cert in duplicate_certs:
        listener_arn = listener_arns_dict.get(duplicate_cert.iam_server_certificate_arn)
        delete_cert_record_and_resource(duplicate_cert, listener_arn)
    
