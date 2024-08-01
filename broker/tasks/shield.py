import logging

from sqlalchemy.orm.attributes import flag_modified

from broker.aws import shield
from broker.extensions import db
from broker.models import Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


class ShieldProtections:
    def __init__(self):
        self.protected_cloudfront_ids: dict[str, str] = {}

    def get_cloudfront_protections(self, should_refresh: bool = False):
        if not self.protected_cloudfront_ids or should_refresh:
            self._list_cloudfront_protections()
        return self.protected_cloudfront_ids

    def _list_cloudfront_protections(self):
        paginator = shield.get_paginator("list_protections")
        response_iterator = paginator.paginate(
            InclusionFilters={"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]},
        )
        for response in response_iterator:
            for protection in response["Protections"]:
                if "ResourceArn" in protection and "Id" in protection:
                    self.protected_cloudfront_ids[protection["ResourceArn"]] = (
                        protection["Id"]
                    )


shield_protections = ShieldProtections()


@huey.retriable_task
def associate_health_checks(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    if not operation:
        raise Exception(f'Could not load operation "{operation_id}" successfully')

    service_instance = operation.service_instance

    operation.step_description = "Associating health checks with Shield"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    logger.info(f'Associating health check(s) for "{service_instance.domain_names}"')

    protected_cloudfront_ids = shield_protections.get_cloudfront_protections()
    protection_id = protected_cloudfront_ids.get(
        service_instance.cloudfront_distribution_arn
    )
    if not protection_id:
        # Do not raise exception here. The Shield protection may not have been created yet.
        logger.info(
            f'Could not find Shield protection for distribution ID "{service_instance.cloudfront_distribution_id}"'
        )
        return

    for health_check in service_instance.route53_health_checks:
        health_check_id = health_check["health_check_id"]
        _associate_health_check(protection_id, health_check_id)
        logger.info(f"Saving associated Route53 health check ID: {health_check_id}")
        service_instance.shield_associated_health_checks.append(
            {
                "health_check_id": health_check_id,
                "protection_id": protection_id,
            }
        )
        flag_modified(service_instance, "shield_associated_health_checks")

    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def update_associated_health_checks(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    if not operation:
        raise Exception(f'Could not load operation "{operation_id}" successfully')

    service_instance = operation.service_instance

    operation.step_description = "Updating associated health checks with Shield"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    logger.info(
        f'Updating associated health check(s) for "{service_instance.domain_names}"'
    )

    protected_cloudfront_ids = shield_protections.get_cloudfront_protections()
    protection_id = protected_cloudfront_ids.get(
        service_instance.cloudfront_distribution_arn
    )
    if not protection_id:
        raise Exception(
            f'Could not find Shield protection for distribution ID "{service_instance.cloudfront_distribution_id}"'
        )

    existing_route53_health_check_ids = [
        check["health_check_id"] for check in service_instance.route53_health_checks
    ]
    shield_associated_health_check_ids = [
        check["health_check_id"]
        for check in service_instance.shield_associated_health_checks
    ]

    # If health check ID is NOT IN the list of associated health check IDs, it needs to be ASSOCIATED
    health_checks_to_associate = [
        check
        for check in service_instance.route53_health_checks
        if check["health_check_id"] not in shield_associated_health_check_ids
    ]

    # If health check is IN the list of associated health checks,
    # but NOT IN the list of created health check IDS,
    # it needs to be DISASSOCIATED
    health_checks_to_disassociate = [
        check
        for check in service_instance.shield_associated_health_checks
        if check["health_check_id"] not in existing_route53_health_check_ids
    ]

    updated_associated_health_checks = service_instance.shield_associated_health_checks

    if len(health_checks_to_associate) > 0:
        updated_associated_health_checks = _associate_health_checks(
            protection_id, updated_associated_health_checks, health_checks_to_associate
        )
        service_instance.shield_associated_health_checks = (
            updated_associated_health_checks
        )
        flag_modified(service_instance, "shield_associated_health_checks")

    if len(health_checks_to_disassociate) > 0:
        health_check_ids_to_disassociate = [
            check["health_check_id"] for check in health_checks_to_disassociate
        ]
        domain_names_to_disassociate = [
            check["domain_name"]
            for check in service_instance.route53_health_checks
            if check["health_check_id"] in health_check_ids_to_disassociate
        ]
        updated_associated_health_checks = _disassociate_health_checks(
            domain_names_to_disassociate,
            updated_associated_health_checks,
            health_checks_to_disassociate,
        )
        service_instance.shield_associated_health_checks = (
            updated_associated_health_checks
        )
        flag_modified(service_instance, "shield_associated_health_checks")

    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def disassociate_health_checks(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    if not operation:
        raise Exception(f'Could not load operation "{operation_id}" successfully')

    service_instance = operation.service_instance

    operation.step_description = "Disassociating health checks with Shield"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    updated_associated_health_checks = _disassociate_health_checks(
        service_instance.domain_names,
        service_instance.shield_associated_health_checks,
        service_instance.shield_associated_health_checks,
    )
    service_instance.shield_associated_health_checks = updated_associated_health_checks
    flag_modified(service_instance, "shield_associated_health_checks")

    db.session.add(service_instance)
    db.session.commit()


def get_health_check_arn(health_check_id):
    # Only the ID, not the ARN is returned by the CreateHealthCheck and
    # GetHealthCheck endpoints. So manually construct the ARN
    return f"arn:aws:route53:::healthcheck/{health_check_id}"


def _associate_health_checks(
    protection_id, associated_health_checks, health_checks_to_associate
):
    for health_check_to_associate in health_checks_to_associate:
        health_check_id = health_check_to_associate["health_check_id"]
        _associate_health_check(protection_id, health_check_id)
        logger.info(f"Saving associated Route53 health check ID: {health_check_id}")
        associated_health_checks.append(
            {
                "health_check_id": health_check_id,
                "protection_id": protection_id,
            }
        )
    return associated_health_checks


def _associate_health_check(protection_id, health_check_id):
    shield.associate_health_check(
        ProtectionId=protection_id,
        HealthCheckArn=get_health_check_arn(health_check_id),
    )
    logger.info(f"Saving associated Route53 health check ID: {health_check_id}")


def _disassociate_health_checks(
    domain_names_to_disassociate, existing_checks, checks_to_disassociate
):
    logger.info(f'Disassociating health check(s) for "{domain_names_to_disassociate}"')

    updated_associated_health_checks = existing_checks
    for health_check_to_disassociate in checks_to_disassociate:
        _disassociate_health_check(health_check_to_disassociate)
        updated_associated_health_checks = [
            check
            for check in updated_associated_health_checks
            if check["health_check_id"]
            != health_check_to_disassociate["health_check_id"]
        ]
    return updated_associated_health_checks


def _disassociate_health_check(health_check):
    health_check_id = health_check["health_check_id"]
    logger.info(f"Removing associated Route53 health check ID: {health_check_id}")

    try:
        shield.disassociate_health_check(
            ProtectionId=health_check["protection_id"],
            HealthCheckArn=get_health_check_arn(health_check_id),
        )
    except shield.exceptions.ResourceNotFoundException:
        logger.info(
            "Associated health check not found",
            extra={
                "protection_id": health_check["protection_id"],
                "health_check_arn": get_health_check_arn(health_check_id),
            },
        )
