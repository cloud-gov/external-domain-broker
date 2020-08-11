from http import HTTPStatus
import logging

from flask import Flask
from openbrokerapi import api as openbrokerapi
from openbrokerapi.helper import to_json_response
from openbrokerapi.response import ErrorResponse

from sap import cf_logging
from sap.cf_logging import flask_logging

# We need to import models, even though it's unused, in order to enable
# `flask db migrate`
from broker import models  # noqa: F401
from broker.api import API
from broker.extensions import config, db, migrate


def create_app():
    app = Flask(__name__)
    cf_logging._SETUP_DONE = False
    flask_logging.init(app)
    logger = logging.getLogger(__name__)
    app.config.from_object(config)

    db.init_app(app)
    migrate.init_app(app, db)

    credentials = openbrokerapi.BrokerCredentials(
        app.config["BROKER_USERNAME"], app.config["BROKER_PASSWORD"]
    )

    app.register_blueprint(openbrokerapi.get_blueprint(API(), credentials, logger))
    del app.error_handler_spec["open_broker"][None][Exception]
    del app.error_handler_spec["open_broker"][None][NotImplementedError]

    # Endpoint to test if server comes up
    @app.route("/ping")
    def ping():
        return "PONG"

    @app.errorhandler(Exception)
    def handle_base_exception(e):
        logger.exception(e)
        return (
            to_json_response(
                ErrorResponse(description="Unhandled error during request")
            ),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    @app.errorhandler(NotImplementedError)
    def handle_not_implemented(e):
        logger.exception(e)
        return (
            to_json_response(ErrorResponse(description="Not Implemented")),
            HTTPStatus.NOT_IMPLEMENTED,
        )

    return app
