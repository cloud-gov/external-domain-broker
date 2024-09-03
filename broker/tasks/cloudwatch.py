import logging

from sqlalchemy.orm.attributes import flag_modified

from broker.aws import cloudwatch_commercial

from broker.extensions import config, db

# from broker.lib.tags import add_tag
from broker.models import Operation, CDNServiceInstance, CDNDedicatedWAFServiceInstance
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

    tags = service_instance.tags if service_instance.tags else []
    service_instance.cloudwatch_health_check_alarm_arns = []

    for health_check in service_instance.route53_health_checks:
        health_check_id = health_check["health_check_id"]
        alarm_arn = _create_health_check_alarm(health_check_id, tags)

        service_instance.cloudwatch_health_check_alarm_arns.append(alarm_arn)
        flag_modified(service_instance, "cloudwatch_health_check_alarm_arns")

    db.session.add(service_instance)
    db.session.commit()


def _create_health_check_alarm(health_check_id, tags) -> str:
    alarm_name = f"{config.CLOUDWATCH_ALARM_NAME_PREFIX}-{health_check_id}"

    # create alarm
    cloudwatch_commercial.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmActions=[config.NOTIFICATIONS_SNS_TOPIC_ARN],
        MetricName="HealthCheckStatus",
        NameSpace="AWS/Route53",
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
        Tags=tags,
    )

    # wait for alarm to exist
    waiter = cloudwatch_commercial.get_waiter("alarm_exists")
    waiter.wait(
        AlarmNames=[alarm_name],
        AlarmTypes=[
            "MetricAlarm",
        ],
    )

    response = cloudwatch_commercial.describe_alarms(AlarmNames=[alarm_name])
    alarms = response["MetricAlarms"]

    if len(alarms) == 0:
        raise RuntimeError(f"Could not find alarm {alarm_name}")
    elif len(alarms) > 1:
        raise RuntimeError(f"Found multiple alarms for {alarm_name}")

    return alarms[0]["AlarmArn"]
