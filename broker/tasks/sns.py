import logging

from botocore.exceptions import ClientError

from broker.aws import sns_commercial

from broker.extensions import config

from broker.tasks.huey import pipeline_operation

logger = logging.getLogger(__name__)


@pipeline_operation("Creating SNS notification topic")
def create_notification_topic(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    sns_kwargs = {}
    if service_instance.sns_notification_topic_arn:
        logger.info(f"Topic already exists for instance {service_instance.id}")
        return

    if service_instance.tags:
        sns_kwargs["Tags"] = service_instance.tags

    response = sns_commercial.create_topic(
        Name=f"{config.AWS_RESOURCE_PREFIX}-{service_instance.id}-notifications",
        **sns_kwargs,
    )
    service_instance.sns_notification_topic_arn = response["TopicArn"]
    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Deleting SNS notification topic")
def delete_notification_topic(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

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
