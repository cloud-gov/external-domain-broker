import logging

from sqlalchemy.orm.attributes import flag_modified

from broker.aws import route53
from broker.extensions import config, db
from broker.models import Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.retriable_task
def create_TXT_records(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Updating DNS TXT records"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    for challenge in [
        c for c in service_instance.new_certificate.challenges if not c.answered
    ]:
        domain = challenge.validation_domain
        txt_record = f"{domain}.{config.DNS_ROOT_DOMAIN}"
        contents = challenge.validation_contents
        logger.info(f'Creating TXT record {txt_record} with contents "{contents}"')
        route53_response = route53.change_resource_record_sets(
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Type": "TXT",
                            "Name": txt_record,
                            "ResourceRecords": [{"Value": f'"{contents}"'}],
                            "TTL": 60,
                        },
                    }
                ]
            },
            HostedZoneId=config.ROUTE53_ZONE_ID,
        )
        change_id = route53_response["ChangeInfo"]["Id"]
        logger.info(f"Saving Route53 TXT change ID: {change_id}")
        service_instance.route53_change_ids.append(change_id)
        flag_modified(service_instance, "route53_change_ids")
        db.session.add(service_instance)
        db.session.commit()


@huey.nonretriable_task
def remove_TXT_records(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Removing DNS TXT records"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    for certificate in service_instance.certificates:
        for challenge in certificate.challenges:
            domain = challenge.validation_domain
            txt_record = f"{domain}.{config.DNS_ROOT_DOMAIN}"
            contents = challenge.validation_contents
            logger.info(f'Removing TXT record {txt_record} with contents "{contents}"')
            try:
                route53_response = route53.change_resource_record_sets(
                    ChangeBatch={
                        "Changes": [
                            {
                                "Action": "DELETE",
                                "ResourceRecordSet": {
                                    "Type": "TXT",
                                    "Name": txt_record,
                                    "ResourceRecords": [{"Value": f'"{contents}"'}],
                                    "TTL": 60,
                                },
                            }
                        ]
                    },
                    HostedZoneId=config.ROUTE53_ZONE_ID,
                )
            except:  # noqa E722
                logger.info("Ignoring error because we don't care")
            else:
                change_id = route53_response["ChangeInfo"]["Id"]
                logger.info(f"Ignoring Route53 TXT change ID: {change_id}")


@huey.retriable_task
def wait_for_changes(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Waiting for DNS changes"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    change_ids = service_instance.route53_change_ids.copy()
    logger.info(f"Waiting for {len(change_ids)} Route53 change IDs: {change_ids}")
    for change_id in change_ids:
        logger.info(f"Waiting for: {change_id}")
        waiter = route53.get_waiter("resource_record_sets_changed")
        waiter.wait(
            Id=change_id,
            WaiterConfig={
                "Delay": config.AWS_POLL_WAIT_TIME_IN_SECONDS,
                "MaxAttempts": config.AWS_POLL_MAX_ATTEMPTS,
            },
        )
        service_instance.route53_change_ids.remove(change_id)
        flag_modified(service_instance, "route53_change_ids")
        db.session.add(service_instance)
        db.session.commit()


@huey.retriable_task
def create_ALIAS_records(operation_id: str, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Creating DNS ALIAS records"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    logger.info(f"Creating ALIAS records for {service_instance.domain_names}")

    for domain in service_instance.domain_names:
        alias_record = f"{domain}.{config.DNS_ROOT_DOMAIN}"
        target = service_instance.domain_internal
        logger.info(f'Creating ALIAS record {alias_record} pointing to "{target}"')
        route53_response = route53.change_resource_record_sets(
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Type": "A",
                            "Name": alias_record,
                            "AliasTarget": {
                                "DNSName": target,
                                "HostedZoneId": service_instance.route53_alias_hosted_zone,
                                "EvaluateTargetHealth": False,
                            },
                        },
                    },
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Type": "AAAA",
                            "Name": alias_record,
                            "AliasTarget": {
                                "DNSName": target,
                                "HostedZoneId": service_instance.route53_alias_hosted_zone,
                                "EvaluateTargetHealth": False,
                            },
                        },
                    },
                ]
            },
            HostedZoneId=config.ROUTE53_ZONE_ID,
        )
        change_id = route53_response["ChangeInfo"]["Id"]
        logger.info(f"Saving Route53 ALIAS change ID: {change_id}")
        service_instance.route53_change_ids.append(change_id)
        flag_modified(service_instance, "route53_change_ids")
        db.session.add(service_instance)
        db.session.commit()


@huey.nonretriable_task
def remove_ALIAS_records(operation_id: str, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Removing DNS ALIAS records"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    logger.info(f"Removing ALIAS records for {service_instance.domain_names}")

    for domain in service_instance.domain_names:
        alias_record = f"{domain}.{config.DNS_ROOT_DOMAIN}"
        target = service_instance.domain_internal
        logger.info(f'Removing ALIAS record {alias_record} pointing to "{target}"')
        try:
            route53_response = route53.change_resource_record_sets(
                ChangeBatch={
                    "Changes": [
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Type": "A",
                                "Name": alias_record,
                                "AliasTarget": {
                                    "DNSName": target,
                                    "HostedZoneId": service_instance.route53_alias_hosted_zone,
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        },
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Type": "AAAA",
                                "Name": alias_record,
                                "AliasTarget": {
                                    "DNSName": target,
                                    "HostedZoneId": service_instance.route53_alias_hosted_zone,
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        },
                    ]
                },
                HostedZoneId=config.ROUTE53_ZONE_ID,
            )
        except:  # noqa E722
            logger.info("Ignoring error because we don't care")
        else:
            change_id = route53_response["ChangeInfo"]["Id"]
            logger.info(f"Not tracking change ID: {change_id}")


@huey.retriable_task
def create_health_checks(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    if not operation:
        return

    service_instance = operation.service_instance

    operation.step_description = "Creating health checks"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    logger.info(f'Creating health check(s) for "{service_instance.domain_names}"')

    created_health_checks = _create_health_checks(
        service_instance,
        service_instance.domain_names,
        service_instance.route53_health_checks,
    )
    service_instance.route53_health_checks = created_health_checks
    flag_modified(service_instance, "route53_health_checks")

    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def create_new_health_checks(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    if not operation:
        return

    service_instance = operation.service_instance

    operation.step_description = "Creating new health checks"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    logger.info(f'Creating new health check(s) for "{service_instance.domain_names}"')

    existing_health_checks = service_instance.route53_health_checks
    existing_health_check_domains = [
        check["domain_name"] for check in service_instance.route53_health_checks
    ]
    # If domain is NOT IN current domains with health checks, it should be CREATED
    health_check_domains_to_create = [
        domain
        for domain in service_instance.domain_names
        if domain not in existing_health_check_domains
    ]

    updated_health_checks = existing_health_checks

    if len(health_check_domains_to_create) > 0:
        updated_health_checks = _create_health_checks(
            service_instance,
            health_check_domains_to_create,
            updated_health_checks,
        )
        service_instance.route53_health_checks = updated_health_checks
        flag_modified(service_instance, "route53_health_checks")

    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def delete_unused_health_checks(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    if not operation:
        return

    service_instance = operation.service_instance

    operation.step_description = "Deleting unused health checks"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    logger.info(
        f'Deleting unused health check(s) for "{service_instance.domain_names}"'
    )

    existing_health_checks = service_instance.route53_health_checks
    # If health check domain is NOT IN updated list of domains, it should be DELETED
    health_checks_to_delete = [
        check
        for check in existing_health_checks
        if check["domain_name"] not in service_instance.domain_names
    ]

    updated_health_checks = existing_health_checks

    if len(health_checks_to_delete) > 0:
        updated_health_checks = _delete_health_checks(
            health_checks_to_delete,
            updated_health_checks,
        )
        service_instance.route53_health_checks = updated_health_checks
        flag_modified(service_instance, "route53_health_checks")

    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def delete_health_checks(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    if not operation:
        return

    service_instance = operation.service_instance

    operation.step_description = "Deleting health checks"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    logger.info(f'Deleting health check(s) for "{service_instance.domain_names}"')

    updated_health_checks = _delete_health_checks(
        service_instance.route53_health_checks, service_instance.route53_health_checks
    )

    service_instance.route53_health_checks = updated_health_checks
    flag_modified(service_instance, "route53_health_checks")

    db.session.add(service_instance)
    db.session.commit()


def _create_health_checks(
    service_instance,
    health_check_domains_to_create,
    existing_health_checks,
):
    tags = service_instance.tags if service_instance.tags else []

    updated_health_checks = existing_health_checks
    for idx, domain_name in enumerate(health_check_domains_to_create):
        health_check_id = _create_health_check(
            idx, service_instance.id, domain_name, tags
        )
        updated_health_checks.append(
            {
                "domain_name": domain_name,
                "health_check_id": health_check_id,
            }
        )
    return sorted(
        updated_health_checks,
        key=lambda check: check["domain_name"],
    )


def _create_health_check(idx, service_instance_id, domain_name, tags):
    logger.info(f"Creating Route53 health check for {domain_name}")
    route53_response = route53.create_health_check(
        CallerReference=f"{service_instance_id}-{idx}",
        HealthCheckConfig={
            "Type": "HTTPS",
            "FullyQualifiedDomainName": domain_name,
        },
    )
    health_check_id = route53_response["HealthCheck"]["Id"]
    logger.info(f"Saving Route53 health check ID: {health_check_id}")
    if len(tags) > 0:
        route53.change_tags_for_resource(
            ResourceType="healthcheck",
            ResourceId=health_check_id,
            AddTags=tags,
        )
    return health_check_id


def _delete_health_checks(health_checks_to_delete, existing_health_checks):
    updated_health_checks = existing_health_checks
    for health_check in health_checks_to_delete:
        health_check_id = health_check["health_check_id"]
        _delete_health_check(health_check_id)
        updated_health_checks = [
            check
            for check in updated_health_checks
            if check["health_check_id"] != health_check_id
        ]
    return updated_health_checks


def _delete_health_check(health_check_id):
    logger.info(f"Deleting Route53 health check ID: {health_check_id}")

    try:
        route53.delete_health_check(
            HealthCheckId=health_check_id,
        )
    except route53.exceptions.NoSuchHealthCheck:
        logger.info(
            "Associated health check not found",
            extra={"health_check_id": health_check_id},
        )
