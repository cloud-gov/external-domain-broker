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

    def get_cloudfront_protections(self):
        if not self.protected_cloudfront_ids:
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

    for health_check_id in service_instance.route53_health_check_ids:
        shield.associate_health_check(
            ProtectionId=protection_id,
            HealthCheckArn=get_health_check_arn(health_check_id),
        )
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


def get_health_check_arn(health_check_id):
    # Only the ID, not the ARN is returned by the CreateHealthCheck and
    # GetHealthCheck endpoints. So manually construct the ARN
    return f"arn:aws:route53:::healthcheck/{health_check_id}"
