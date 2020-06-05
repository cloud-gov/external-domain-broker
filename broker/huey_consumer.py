from sap import cf_logging

from broker.app import create_app

if not cf_logging._SETUP_DONE:
    cf_logging.init()

app = create_app()

with app.app_context():
    from broker.tasks import pipelines  # noqa F401
    from broker.tasks.huey import huey  # noqa F401
