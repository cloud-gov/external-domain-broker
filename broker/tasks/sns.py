import logging

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
