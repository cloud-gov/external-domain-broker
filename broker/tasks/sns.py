import logging

from botocore.exceptions import ClientError

from sqlalchemy.orm.attributes import flag_modified

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


@pipeline_operation("Subscribing to SNS notification topic")
def subscribe_notification_topic(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if service_instance.sns_notification_topic_subscription_arn:
        logger.info(f"Subscription already exists for instance {service_instance.id}")
        return

    if not service_instance.sns_notification_topic_arn:
        raise RuntimeError(
            f"SNS topic is required to create a subscription, none found for {service_instance.id}"
        )

    if not service_instance.alarm_notification_email:
        raise RuntimeError(
            f"alarm_notification_email must be specified to create a subscription, none found on {service_instance.id}"
        )

    response = sns_commercial.subscribe(
        TopicArn=service_instance.sns_notification_topic_arn,
        Protocol="email",
        Endpoint=service_instance.alarm_notification_email,
        ReturnSubscriptionArn=True,
    )
    service_instance.sns_notification_topic_subscription_arn = response[
        "SubscriptionArn"
    ]
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


@pipeline_operation("Unsubscribing from SNS notification topic")
def unsubscribe_notification_topic(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if not service_instance.sns_notification_topic_subscription_arn:
        logger.info(
            f"No SNS topic subscription to delete for instance {service_instance.id}"
        )
        return

    try:
        sns_commercial.unsubscribe(
            SubscriptionArn=service_instance.sns_notification_topic_subscription_arn
        )
    except ClientError as e:
        if "NotFound" in e.response["Error"]["Code"]:
            logger.info(
                "SNS topic subscription not found",
                extra={
                    "subscription_arn": service_instance.sns_notification_topic_subscription_arn
                },
            )
        elif (
            "InvalidParameter" in e.response["Error"]["Code"]
            and "pending confirmation" in e.response["Error"]["Message"]
        ):
            logger.info(
                "No need to unsubscribe, subscription still pending",
                extra={
                    "subscription_arn": service_instance.sns_notification_topic_subscription_arn
                },
            )
        else:
            logger.error(
                f"Got this error code unsubscribing {service_instance.sns_notification_topic_subscription_arn}: {e.response['Error']}"
            )
            raise e

    service_instance.sns_notification_topic_subscription_arn = None
    db.session.add(service_instance)
    db.session.commit()
