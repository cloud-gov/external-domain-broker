import logging

from flask import Flask
from openbrokerapi import api as openbrokerapi
from sap import cf_logging
from sap.cf_logging import flask_logging

# We need to import models, even though it's unused, in order to enable
# `flask db migrate`
from broker import models  # noqa: F401
from broker.extensions import (
    db,
    huey,
    config,
    migrate,
)
from broker.api import API


def create_app():

    app = Flask(__name__)
    cf_logging._SETUP_DONE = False
    flask_logging.init(app)
    logger = logging.getLogger(__name__)
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
