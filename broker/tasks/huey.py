import logging

from huey import RedisHuey

from sap import cf_logging
from broker.extensions import config

logger = logging.getLogger(__name__)

huey = RedisHuey(
    host=config.REDIS_HOST, port=config.REDIS_PORT, password=config.REDIS_PASSWORD, ssl=True, ssl_cert_reqs=None
)

# Normal task, no retries
nonretriable_task = huey.task()

# These tasks retry every 10 minutes for a day.
retriable_task = huey.task(retries=(6 * 24), retry_delay=(60 * 10))


@huey.pre_execute(name="Set Correlation ID")
def register_correlation_id(task):
    args, kwargs = task.data
    correlation_id = kwargs.pop("correlation_id", "Rogue Task")
    cf_logging.FRAMEWORK.context.set_correlation_id(correlation_id)


@huey.signal()
def log_task_transition(signal, task, exc=None):
    args, kwargs = task.data
    extra = dict(operation_id=args[0], task_id=task.id, signal=signal)
    logger.info("task signal received", extra=extra)
    if exc is not None:
        logger.exception(msg="task raised exception", extra=extra, exc_info=exc)
