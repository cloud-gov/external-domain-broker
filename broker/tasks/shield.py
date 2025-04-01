import logging

from sqlalchemy.orm.attributes import flag_modified

from broker.aws import shield
from broker.lib.shield_protections import ShieldProtections
from broker.tasks.huey import pipeline_operation

logger = logging.getLogger(__name__)

shield_protections = ShieldProtections(shield)


@pipeline_operation("Associating health check with Shield")
def associate_health_check(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    logger.info(f'Associating health check(s) for "{service_instance.domain_names}"')

    protection_id = _get_cloudfront_shield_protection_id(service_instance)

    if len(service_instance.route53_health_checks) > 0:
        # We can only associate one health check to a Shield protection at a time,
        # so arbitrarily choose the first one
        health_check = service_instance.route53_health_checks[0]

        shield_associated_health_check = _associate_health_check(
            health_check["domain_name"], protection_id, health_check["health_check_id"]
        )
        service_instance.shield_associated_health_check = shield_associated_health_check

        flag_modified(service_instance, "shield_associated_health_check")
        db.session.add(service_instance)
        db.session.commit()


@pipeline_operation("Updating associated health check with Shield")
def update_associated_health_check(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    logger.info(
        f'Updating associated health check(s) for "{service_instance.domain_names}"'
    )

    if service_instance.shield_associated_health_check:
        shield_associated_health_check_domain_name = (
            service_instance.shield_associated_health_check["domain_name"]
        )

        # IF the domain name for associated health check is NOT IN the list of domain names,
        # THEN it needs to be DISASSOCIATED
        if (
            shield_associated_health_check_domain_name
            not in service_instance.domain_names
        ):
            _disassociate_health_check(service_instance.shield_associated_health_check)
            service_instance.shield_associated_health_check = None
            flag_modified(service_instance, "shield_associated_health_check")

    # IF the domain name for associated health check is IN the list of domain names
    # AND there is not already an existing associated health check,
    # THEN it needs to be ASSOCIATED
    if not service_instance.shield_associated_health_check:
        health_checks_to_associate = [
            check
            for check in service_instance.route53_health_checks
            if check["domain_name"] in service_instance.domain_names
        ]

        if len(health_checks_to_associate) > 0:
            protection_id = _get_cloudfront_shield_protection_id(service_instance)
            # We can only associate one health check to a Shield protection at a time
            health_check = health_checks_to_associate[0]
            shield_associated_health_check = _associate_health_check(
                health_check["domain_name"],
                protection_id,
                health_check["health_check_id"],
            )
            service_instance.shield_associated_health_check = (
                shield_associated_health_check
            )
            flag_modified(service_instance, "shield_associated_health_check")

    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Disassociating health check with Shield")
def disassociate_health_check(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    shield_associated_health_check = service_instance.shield_associated_health_check
    if shield_associated_health_check is None or shield_associated_health_check == {}:
        logger.info("No health check to disassociate from Shield")
        return

    _disassociate_health_check(
        shield_associated_health_check,
    )
    service_instance.shield_associated_health_check = None
    flag_modified(service_instance, "shield_associated_health_check")

    db.session.add(service_instance)
    db.session.commit()


def get_health_check_arn(health_check_id):
    # Only the ID, not the ARN is returned by the CreateHealthCheck and
    # GetHealthCheck endpoints. So manually construct the ARN
    return f"arn:aws:route53:::healthcheck/{health_check_id}"


def _associate_health_check(domain_name, protection_id, health_check_id):
    shield.associate_health_check(
        ProtectionId=protection_id,
        HealthCheckArn=get_health_check_arn(health_check_id),
    )
    logger.info(f"Saving associated Route53 health check ID: {health_check_id}")
    return {
        "domain_name": domain_name,
        "health_check_id": health_check_id,
        "protection_id": protection_id,
    }


def _disassociate_health_check(health_check):
    health_check_id = health_check["health_check_id"]
    protection_id = health_check["protection_id"]
    logger.info(f"Removing associated Route53 health check ID: {health_check_id}")

    try:
        shield.disassociate_health_check(
            ProtectionId=protection_id,
            HealthCheckArn=get_health_check_arn(health_check_id),
        )
    except shield.exceptions.ResourceNotFoundException:
        logger.info(
            "Associated health check not found",
            extra={
                "protection_id": protection_id,
                "health_check_arn": get_health_check_arn(health_check_id),
            },
        )


def _get_cloudfront_shield_protection_id(service_instance):
    protected_cloudfront_ids = shield_protections.get_cloudfront_protections(
        should_refresh=True
    )
    protection_id = protected_cloudfront_ids.get(
        service_instance.cloudfront_distribution_arn
    )
    if not protection_id:
        raise Exception(
            f'Could not find Shield protection for distribution ID "{service_instance.cloudfront_distribution_id}"'
        )
    return protection_id
