import logging

from flask import Flask
from redis import ConnectionPool, SSLConnection
from huey import RedisHuey, signals

from sap import cf_logging
from broker.extensions import config, db
from broker.models import Operation
from broker.smtp import send_failed_operation_alert

logger = logging.getLogger(__name__)

if config.REDIS_SSL:
    redis_kwargs = dict(connection_class=SSLConnection, ssl_cert_reqs=None)
else:
    redis_kwargs = dict()

connection_pool = ConnectionPool(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    password=config.REDIS_PASSWORD,
    **redis_kwargs,
)
huey = RedisHuey(connection_pool=connection_pool)

# these two lines need to be here so we can define [non]retriable_task
huey.flask_app = Flask(__name__)
huey.flask_app.config.from_object(config)

# this line is so this all works the same in tests
db.init_app(huey.flask_app)

# Normal task, no retries
nonretriable_task = huey.context_task(huey.flask_app.app_context())

# These tasks retry every 10 minutes for a day.
retriable_task = huey.context_task(
    huey.flask_app.app_context(), retries=6 * 24, retry_delay=10 * 60
)


@huey.on_startup()
def create_app():
    app = Flask(__name__)
    app.config.from_object(config)
    huey.flask_app = app
    db.init_app(app)


@huey.on_startup()
def initialize_logging():
    cf_logging.init()


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


@huey.signal(signals.SIGNAL_ERROR)
def mark_operation_failed(signal, task, exc=None):
    args, kwargs = task.data
    if task.retries:
        return
    try:
        operation = Operation.query.get(args[0])
    except:
        # assume this task doesn't follow our pattern of operation_id as the first param
        # in which case this task is not a part of a provisioning/upgrade/deprovisioning pipeline
        return
    operation.state = Operation.States.FAILED.value
    send_failed_operation_alert(operation)
    db.session.add(operation)
    db.session.commit()
