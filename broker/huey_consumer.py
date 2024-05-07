import logging
from sap import cf_logging

# we need to init the logging before we import anything else in order for it to work
cf_logging.init()

# this is kinda brute-force.
# cf_logging sets the logger class with logging.setLoggerClass(CfLogger) but because we're
# entering through huey_consumer.py, the `huey` logger has already been initialized with
# the default logger class. To work around that, we're reusing the logRecordFactory that
# the CfLogger uses under the hood. For some reason, cf_logging reorders args, so the kwarg
# `extra` is the first param to SimpleLogRecord.
logging.setLogRecordFactory(
    lambda *args, **kwargs: cf_logging.record.simple_log_record.SimpleLogRecord(
        kwargs.get("extra"), cf_logging.FRAMEWORK, *args, **kwargs
    )
)

from broker.app import create_app  # noqa F401
from broker.tasks.huey import huey  # noqa F401
from broker.tasks import pipelines, cron  # noqa F401
