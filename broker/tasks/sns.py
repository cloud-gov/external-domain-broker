import logging

from botocore.exceptions import ClientError
from sqlalchemy.orm.attributes import flag_modified

from broker.aws import sns_commercial

from broker.extensions import config, db

from broker.models import Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.retriable_task
def create_notification_topic(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Creating SNS notification topic"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    kwargs = {}
    if service_instance.tags:
        kwargs["Tags"] = service_instance.tags

    response = sns_commercial.create_topic(
        Name=f"{config.AWS_RESOURCE_PREFIX}-{service_instance.id}-notifications",
        **kwargs,
    )
    service_instance.sns_notification_topic_arn = response["TopicArn"]
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def delete_notification_topic(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Deleting SNS notification topic"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if not service_instance.sns_notification_topic_arn:
        logger.info(f"No SNS topic to delete for instance {service_instance.id}")
        return

    try:
        sns_commercial.delete_topic(
            TopicArn=service_instance.sns_notification_topic_arn
        )
    except ClientError as e:
        if "NotFound" in e.response["Error"]["Code"]:
            logger.info(
                "SNS topic not found",
                extra={"topic_arn": service_instance.sns_notification_topic_arn},
            )
        else:
            logger.error(
                f"Got this error code deleting SNS topic {service_instance.sns_notification_topic_arn}: {e.response['Error']}"
            )
            raise e

    service_instance.sns_notification_topic_arn = None
    db.session.add(service_instance)
    db.session.commit()
