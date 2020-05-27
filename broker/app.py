import logging

from flask import Flask
from openbrokerapi import api as openbrokerapi

# We need to import models, even though it's unused, in order to enable
# `flask db migrate`
from broker import models  # noqa: F401
from broker.api import API
from broker.extensions import (
    db,
    huey,
    config,
    migrate,
)

logger = logging.getLogger(__name__)


def create_app():

    app = Flask(__name__)
    app.config.from_object(config)
    app.huey = huey

    db.init_app(app)
    migrate.init_app(app, db)

    credentials = openbrokerapi.BrokerCredentials(
        app.config["BROKER_USERNAME"], app.config["BROKER_PASSWORD"]
    )

    app.register_blueprint(openbrokerapi.get_blueprint(API(), credentials, logger))

    # Endpoint to test if server comes up
    @app.route("/ping")
    def ping():
        return "PONG"

    return app
