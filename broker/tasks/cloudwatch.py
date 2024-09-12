import logging

from botocore.exceptions import ClientError
from sqlalchemy.orm.attributes import flag_modified

from broker.aws import cloudwatch_commercial

from broker.extensions import config, db

from broker.models import Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.retriable_task
def create_health_check_alarms(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Creating Cloudwatch alarms for Route53 health checks"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if len(service_instance.route53_health_checks) == 0:
        logger.info(
            f"No Route53 health checks to create alarms on instance {service_instance.id}"
        )
        return

    new_health_check_alarms = _create_health_check_alarms(
        service_instance.route53_health_checks, [], service_instance.tags
    )
    service_instance.cloudwatch_health_check_alarms = new_health_check_alarms
    flag_modified(service_instance, "cloudwatch_health_check_alarms")

    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def update_health_check_alarms(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Updating Cloudwatch alarms for Route53 health checks"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if len(service_instance.route53_health_checks) == 0:
        logger.info(
            f"No Route53 health checks to update alarms on instance {service_instance.id}"
        )
        return

    existing_route53_health_check_ids = [
        health_check["health_check_id"]
        for health_check in service_instance.route53_health_checks
    ]

    if service_instance.cloudwatch_health_check_alarms == None:
        existing_health_check_alarms = []
    else:
        existing_health_check_alarms = service_instance.cloudwatch_health_check_alarms
    existing_cloudwatch_alarm_health_check_ids = [
        health_check["health_check_id"] for health_check in existing_health_check_alarms
    ]

    updated_health_check_alarms = existing_health_check_alarms

    # IF a health check ID for a Cloudwatch alarm
    # IS NOT in the set of existing Route53 health check IDs for this service
    # THEN the Cloudwatch alarm for the health check ID(s) should be DELETED
    health_checks_alarm_names_to_delete = [
        health_check_alarm["alarm_name"]
        for health_check_alarm in existing_health_check_alarms
        if health_check_alarm["health_check_id"]
        not in existing_route53_health_check_ids
    ]
    if len(health_checks_alarm_names_to_delete) > 0:
        updated_health_check_alarms = _delete_alarms(
            updated_health_check_alarms, health_checks_alarm_names_to_delete
        )
        service_instance.cloudwatch_health_check_alarms = updated_health_check_alarms
        flag_modified(service_instance, "cloudwatch_health_check_alarms")

    # IF a health check ID for a Route53 health check
    # IS NOT in the set of existing health check IDs for Cloudwatch alarms for this service
    # THEN the Cloudwatch alarm for the health check ID should be CREATED
    health_checks_to_create_alarms = [
        health_check
        for health_check in service_instance.route53_health_checks
        if health_check["health_check_id"]
        not in existing_cloudwatch_alarm_health_check_ids
    ]
    if len(health_checks_to_create_alarms) > 0:
        updated_health_check_alarms = _create_health_check_alarms(
            health_checks_to_create_alarms,
            updated_health_check_alarms,
            service_instance.tags,
        )
        service_instance.cloudwatch_health_check_alarms = updated_health_check_alarms
        flag_modified(service_instance, "cloudwatch_health_check_alarms")

    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def delete_health_check_alarms(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Deleting Cloudwatch alarms for Route53 health checks"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if service_instance.cloudwatch_health_check_alarms == None:
        existing_health_check_alarms = []
    else:
        existing_health_check_alarms = service_instance.cloudwatch_health_check_alarms

    health_checks_alarm_names_to_delete = [
        health_check_alarm["alarm_name"]
        for health_check_alarm in existing_health_check_alarms
    ]

    if len(health_checks_alarm_names_to_delete) > 0:
        updated_health_check_alarms = _delete_alarms(
            existing_health_check_alarms, health_checks_alarm_names_to_delete
        )
        service_instance.cloudwatch_health_check_alarms = updated_health_check_alarms
        flag_modified(service_instance, "cloudwatch_health_check_alarms")

    db.session.add(service_instance)
    db.session.commit()


def _create_health_check_alarms(
    health_checks_to_create_alarms, existing_health_check_alarms, tags
):
    for health_check in health_checks_to_create_alarms:
        health_check_id = health_check["health_check_id"]
        alarm_name = _create_health_check_alarm(health_check_id, tags)

        existing_health_check_alarms.append(
            {
                "alarm_name": alarm_name,
                "health_check_id": health_check_id,
            }
        )
    return existing_health_check_alarms


def _create_health_check_alarm(health_check_id, tags) -> str:
    alarm_name = _get_alarm_name(health_check_id)

    # create alarm
    kwargs = {}
    if tags:
        kwargs["Tags"] = tags

    cloudwatch_commercial.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmActions=[config.NOTIFICATIONS_SNS_TOPIC_ARN],
        MetricName="HealthCheckStatus",
        Namespace="AWS/Route53",
        Statistic="Minimum",
        Dimensions=[
            {
                "Name": "HealthCheckId",
                "Value": health_check_id,
            }
        ],
        Period=60,
        EvaluationPeriods=1,
        DatapointsToAlarm=1,
        Threshold=1,
        ComparisonOperator="LessThanThreshold",
        **kwargs,
    )

    # wait for alarm to exist
    waiter = cloudwatch_commercial.get_waiter("alarm_exists")
    waiter.wait(
        AlarmNames=[alarm_name],
        AlarmTypes=[
            "MetricAlarm",
        ],
        WaiterConfig={
            "Delay": config.AWS_POLL_WAIT_TIME_IN_SECONDS,
            "MaxAttempts": config.AWS_POLL_MAX_ATTEMPTS,
        },
    )

    return alarm_name


def _delete_alarms(existing_health_check_alarms, alarm_names_to_delete):
    try:
        cloudwatch_commercial.delete_alarms(AlarmNames=alarm_names_to_delete)
    except ClientError as e:
        if "ResourceNotFound" in e.response["Error"]["Code"]:
            logger.info(
                "Cloudwatch alarms not found",
                extra={"alarm_names": alarm_names_to_delete},
            )
        else:
            logger.error(
                f"Got this error code deleting Cloudwatch alarms: {e.response['Error']}"
            )
            raise e
    existing_health_check_alarms = [
        health_check_alarm
        for health_check_alarm in existing_health_check_alarms
        if health_check_alarm["alarm_name"] not in alarm_names_to_delete
    ]
    return existing_health_check_alarms


def _get_alarm_name(health_check_id):
    return f"{config.CLOUDWATCH_ALARM_NAME_PREFIX}-{health_check_id}"
