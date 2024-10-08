import logging

from botocore.exceptions import ClientError

from sqlalchemy.orm.attributes import flag_modified

from broker.aws import cloudwatch_commercial
from broker.extensions import config
from broker.tasks.huey import pipeline_operation

logger = logging.getLogger(__name__)


@pipeline_operation("Creating Cloudwatch alarms for Route53 health checks")
def create_health_check_alarms(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if not service_instance.sns_notification_topic_arn:
        raise RuntimeError(
            f"Could not find sns_notification_topic_arn for instance {service_instance.id}"
        )

    if len(service_instance.route53_health_checks) == 0:
        logger.info(
            f"No Route53 health checks to create alarms on instance {service_instance.id}"
        )
        return

    new_health_check_alarms = _create_health_check_alarms(
        service_instance.route53_health_checks,
        [],
        service_instance.sns_notification_topic_arn,
        service_instance.tags,
    )
    service_instance.cloudwatch_health_check_alarms = new_health_check_alarms
    flag_modified(service_instance, "cloudwatch_health_check_alarms")

    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Deleting Cloudwatch alarms for Route53 health checks")
def delete_health_check_alarms(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if service_instance.cloudwatch_health_check_alarms is None:
        existing_health_check_alarms = []
    else:
        existing_health_check_alarms = service_instance.cloudwatch_health_check_alarms

    health_checks_alarm_names_to_delete = [
        health_check_alarm["alarm_name"]
        for health_check_alarm in existing_health_check_alarms
    ]

    if len(health_checks_alarm_names_to_delete) > 0:
        updated_health_check_alarms = _delete_cloudwatch_health_check_alarms(
            existing_health_check_alarms, health_checks_alarm_names_to_delete
        )
        service_instance.cloudwatch_health_check_alarms = updated_health_check_alarms
        flag_modified(service_instance, "cloudwatch_health_check_alarms")

    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Creating DDoS detection alarm")
def create_ddos_detected_alarm(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if not service_instance.sns_notification_topic_arn:
        raise RuntimeError(
            f"Could not find sns_notification_topic_arn for instance {service_instance.id}"
        )

    if service_instance.ddos_detected_cloudwatch_alarm_name:
        logger.info(
            f"DDoS alarm name {service_instance.ddos_detected_cloudwatch_alarm_name} already exists"
        )
        return

    ddos_detected_alarm_name = generate_ddos_alarm_name(service_instance.id)
    _create_cloudwatch_alarm(
        generate_ddos_alarm_name(service_instance.id),
        service_instance.sns_notification_topic_arn,
        service_instance.tags,
        MetricName="DDoSDetected",
        Namespace="AWS/DDoSProtection",
        Statistic="Maximum",
        Dimensions=[
            {
                "Name": "ResourceArn",
                "Value": service_instance.cloudfront_distribution_arn,
            }
        ],
        ComparisonOperator="GreaterThanOrEqualToThreshold",
    )
    service_instance.ddos_detected_cloudwatch_alarm_name = ddos_detected_alarm_name
    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Deleting DDoS detection alarm")
def delete_ddos_detected_alarm(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if not service_instance.ddos_detected_cloudwatch_alarm_name:
        return

    _delete_alarms([service_instance.ddos_detected_cloudwatch_alarm_name])
    service_instance.ddos_detected_cloudwatch_alarm_name = None
    db.session.add(service_instance)
    db.session.commit()


def _create_health_check_alarms(
    health_checks_to_create_alarms,
    existing_health_check_alarms,
    sns_notification_topic_arn,
    tags,
):
    for health_check in health_checks_to_create_alarms:
        health_check_id = health_check["health_check_id"]
        alarm_name = _create_health_check_alarm(
            health_check_id, sns_notification_topic_arn, tags
        )

        existing_health_check_alarms.append(
            {
                "alarm_name": alarm_name,
                "health_check_id": health_check_id,
            }
        )
    return existing_health_check_alarms


def _create_health_check_alarm(
    health_check_id, sns_notification_topic_arn, tags
) -> str:
    alarm_name = _get_alarm_name(health_check_id)

    _create_cloudwatch_alarm(
        alarm_name,
        sns_notification_topic_arn,
        tags,
        MetricName="HealthCheckStatus",
        Namespace="AWS/Route53",
        Statistic="Minimum",
        Dimensions=[
            {
                "Name": "HealthCheckId",
                "Value": health_check_id,
            }
        ],
        ComparisonOperator="LessThanThreshold",
    )
    return alarm_name


def _create_cloudwatch_alarm(alarm_name, notification_sns_topic_arn, tags, **kwargs):
    if tags:
        kwargs["Tags"] = tags

    cloudwatch_commercial.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmActions=[notification_sns_topic_arn],
        Period=60,
        EvaluationPeriods=1,
        DatapointsToAlarm=1,
        Threshold=1,
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


def _delete_cloudwatch_health_check_alarms(
    existing_health_check_alarms, alarm_names_to_delete
):
    _delete_alarms(alarm_names_to_delete)
    existing_health_check_alarms = [
        health_check_alarm
        for health_check_alarm in existing_health_check_alarms
        if health_check_alarm["alarm_name"] not in alarm_names_to_delete
    ]
    return existing_health_check_alarms


def _delete_alarms(alarm_names_to_delete):
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


def generate_ddos_alarm_name(service_instance_id):
    return f"{config.AWS_RESOURCE_PREFIX}-{service_instance_id}-DDoSDetected"


def _get_alarm_name(health_check_id):
    return f"{config.AWS_RESOURCE_PREFIX}-{health_check_id}"
