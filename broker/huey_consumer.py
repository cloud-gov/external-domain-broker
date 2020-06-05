from sap import cf_logging
from broker.tasks import pipelines  # noqa F401
from broker.tasks.huey import huey  # noqa F401

if not cf_logging._SETUP_DONE:
    cf_logging.init()
