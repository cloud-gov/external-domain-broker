import logging
import time

from sqlalchemy import func, select, desc

from broker.aws import alb, iam_govcloud
from broker.extensions import config, db
from broker.models import ALBServiceInstance, DedicatedALBServiceInstance, Certificate
from broker.tasks.iam import _delete_server_certificate

logger = logging.getLogger(__name__)


def find_duplicate_alb_certs(service_instance_model):
    query = (
        select(
            service_instance_model.id, func.count(Certificate.id).label("cert_count")
        )
        .select_from(Certificate)
        .join(
            service_instance_model,
            service_instance_model.id == Certificate.service_instance_id,
        )
        .where(service_instance_model.current_certificate_id != Certificate.id)
        .group_by(service_instance_model.id)
        .having(func.count(Certificate.id) > 0)
        .order_by(desc("cert_count"))
    )
    return db.session.execute(query).fetchall()


def get_service_duplicate_alb_cert_count(service_instance_id, service_instance_model):
    query = (
        select(
            Certificate.id,
        )
        .select_from(Certificate)
        .join(
            service_instance_model,
            service_instance_model.id == Certificate.service_instance_id,
        )
        .where(
            (service_instance_model.current_certificate_id != Certificate.id)
            & (Certificate.service_instance_id == service_instance_id)
        )
    )
    results = db.session.execute(query).fetchall()
    return len(results)


def get_duplicate_certs_for_service(service_instance_id, service_instance_model):
    return (
        Certificate.query.join(
            service_instance_model,
            service_instance_model.id == Certificate.service_instance_id,
        )
        .filter(
            Certificate.service_instance_id == service_instance_id,
            Certificate.id != service_instance_model.current_certificate_id,
        )
        .where(service_instance_model.current_certificate_id != Certificate.id)
        .all()
    )


def log_duplicate_cert_count_metric(service_instance_id, num_duplicates, logger=logger):
    logger.info(
        f'service_instance_duplicate_cert_count{{service_instance_id="{service_instance_id}"}} {num_duplicates}'
    )


def get_and_log_service_duplicate_alb_cert_metric(
    service_instance_id, service_instance_model, logger=logger
):
    num_duplicates = get_service_duplicate_alb_cert_count(
        service_instance_id, service_instance_model
    )
    # Log metric of remaining duplicate count so Prometheus is updated
    log_duplicate_cert_count_metric(service_instance_id, num_duplicates, logger=logger)


def log_duplicate_alb_cert_metrics(
    service_instance_model=ALBServiceInstance, logger=logger
):
    service_instance_models = [ALBServiceInstance, DedicatedALBServiceInstance]
    for service_instance_model in service_instance_models:
        for duplicate_result in find_duplicate_alb_certs(service_instance_model):
            [service_instance_id, num_duplicates] = duplicate_result
            log_duplicate_cert_count_metric(
                service_instance_id, num_duplicates, logger=logger
            )


def delete_duplicate_cert_db_record(duplicate_cert):
    certificate = Certificate.query.filter(Certificate.id == duplicate_cert.id).first()
    db.session.delete(certificate)


def get_listener_cert_arns(listener_arn, alb=alb):
    response = alb.describe_listener_certificates(
        ListenerArn=listener_arn,
    )
    listener_cert_arns = [cert["CertificateArn"] for cert in response["Certificates"]]
    return listener_cert_arns


def verify_listener_certificate_is_removed(listener_arn, certificate_arn, alb=alb):
    listener_cert_arns = get_listener_cert_arns(listener_arn, alb=alb)
    return certificate_arn not in listener_cert_arns


def remove_certificate_from_listener_and_verify_removal(
    listener_arn, certificate_arn, alb=alb
):
    alb.remove_listener_certificates(
        ListenerArn=listener_arn, Certificates=[{"CertificateArn": certificate_arn}]
    )

    is_removed = False
    attempts = 0

    while not is_removed and attempts < config.AWS_POLL_MAX_ATTEMPTS:
        attempts += 1
        is_removed = verify_listener_certificate_is_removed(
            listener_arn, certificate_arn, alb=alb
        )
        time.sleep(config.AWS_POLL_WAIT_TIME_IN_SECONDS)

    if is_removed:
        logger.info(
            f"Removed certificate {certificate_arn} from listener {listener_arn}"
        )
    else:
        logger.info(
            f"Could not verify certificate {certificate_arn} was removed from listener {listener_arn} after {config.AWS_POLL_MAX_ATTEMPTS} tries, giving up"
        )
    return is_removed


def delete_cert_record_and_resource(
    certificate,
    listener_arn,
    alb=alb,
    db=db,
    logger=logger,
):
    try:
        delete_duplicate_cert_db_record(certificate)

        if listener_arn:
            remove_certificate_from_listener_and_verify_removal(
                listener_arn, certificate.iam_server_certificate_arn, alb=alb
            )

        if certificate.iam_server_certificate_name:
            _delete_server_certificate(iam_govcloud, certificate)

        # only commit deletion if previous operations were successful
        db.session.commit()

        logger.info(
            f"Deleted duplicate certificate {certificate.id} for service instance {certificate.service_instance_id}"
        )
    except Exception as e:
        logger.error(f"Exception while deleting certificate: {e}")
        db.session.rollback()


def get_matching_alb_listener_arns_for_cert_arns(
    duplicate_cert_arns, listener_arns, alb=alb
):
    matched_listeners_dict = {}
    all_matched_cert_arns = []
    for listener_arn in listener_arns:
        listener_cert_arns = get_listener_cert_arns(listener_arn, alb=alb)
        # Get list of duplicate cert ARNs that were matched for this ALB listener ARN
        matched_cert_arns = list(set(listener_cert_arns) & set(duplicate_cert_arns))

        if len(matched_cert_arns) > 0:
            # Update dict of cert ARNs to ALB listener ARNs
            matched_listeners_dict.update(
                dict(zip(matched_cert_arns, [listener_arn] * len(matched_cert_arns)))
            )
            all_matched_cert_arns = all_matched_cert_arns + matched_cert_arns
            # We have matched all the duplicate cert ARNs, so break out of loop
            if len(all_matched_cert_arns) == len(duplicate_cert_arns):
                break
    return matched_listeners_dict


def remove_duplicate_alb_certs(
    alb_listener_arns: list[str] = config.ALB_LISTENER_ARNS,
    dedicated_listener_arn_map: dict[str] = config.DEDICATED_ALB_LISTENER_ARN_MAP,
    logger=logger,
):
    service_instance_models = [ALBServiceInstance, DedicatedALBServiceInstance]

    for service_instance_model in service_instance_models:
        if service_instance_model == ALBServiceInstance:
            listener_arns = alb_listener_arns
        elif service_instance_model == DedicatedALBServiceInstance:
            listener_arns = list(dedicated_listener_arn_map.keys())
        else:
            # It is not really possible for this condition to be reached, but adding belt/suspenders
            # in case of later code refactoring
            raise Exception(
                f"Could not find listener ARNs for model {service_instance_model}"
            )

        for duplicate_result in find_duplicate_alb_certs(service_instance_model):
            [service_instance_id, num_duplicates] = duplicate_result

            service_instance = db.session.get(
                service_instance_model, service_instance_id
            )
            if service_instance.has_active_operations():
                logger.info(
                    f"Instance {service_instance_id} has an active operation in progress, so duplicate certificates cannot be removed. Try again in a few minutes."
                )
                continue

            logger.info(
                f"Found {num_duplicates} duplicate certificates for service instance {service_instance_id}"
            )

            duplicate_certs = get_duplicate_certs_for_service(
                service_instance_id, service_instance_model
            )
            duplicate_cert_arns = [
                cert.iam_server_certificate_arn for cert in duplicate_certs
            ]

            # Get dictionary for reverse lookup of listener ARN by certificate ARN
            listener_arns_dict = get_matching_alb_listener_arns_for_cert_arns(
                duplicate_cert_arns, listener_arns
            )

            for duplicate_cert in duplicate_certs:
                listener_arn = listener_arns_dict.get(
                    duplicate_cert.iam_server_certificate_arn
                )
                delete_cert_record_and_resource(
                    duplicate_cert, listener_arn, logger=logger
                )

            # Get and log metric of remaining count of duplicates so Prometheus is updated
            get_and_log_service_duplicate_alb_cert_metric(
                service_instance_id, service_instance_model, logger=logger
            )
