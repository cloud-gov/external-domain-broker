from broker.app import create_app
from broker.tasks.huey import huey  # noqa F401

huey.immediate = True