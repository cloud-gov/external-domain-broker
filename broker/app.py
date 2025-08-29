from http import HTTPStatus
import logging
import sys

from flask import Flask
from openbrokerapi import api as openbrokerapi
from openbrokerapi.helper import to_json_response
from openbrokerapi.response import ErrorResponse

from sap import cf_logging
from sap.cf_logging import flask_logging

# We need to import models, even though it's unused, in order to enable
# `flask db migrate`
from broker import models  # noqa: F401
from broker.api import API, ClientError
from broker.commands.duplicate_certs import (
    log_duplicate_alb_cert_metrics,
    remove_duplicate_alb_certs,
)
from broker.commands.tags import add_dedicated_alb_tags
from broker.commands.waf import (
    create_dedicated_alb_waf_web_acls,
    associate_dedicated_alb_waf_web_acls,
)
from broker.extensions import config, db, migrate
from broker.errors import handle_exception


def create_app():
    app = Flask(__name__)
    cf_logging._SETUP_DONE = False
    flask_logging.init(app)
    logger = logging.getLogger(__name__)
    app.config.from_object(config)

    sys.excepthook = handle_exception

    db.init_app(app)
    migrate.init_app(app, db)

    credentials = openbrokerapi.BrokerCredentials(
        app.config["BROKER_USERNAME"], app.config["BROKER_PASSWORD"]
    )

    app.register_blueprint(openbrokerapi.get_blueprint(API(), credentials, logger))

    # drop the upstream's error-handlers, because they dump error messages to the cient
    del app.error_handler_spec["open_broker"][None][Exception]
    del app.error_handler_spec["open_broker"][None][NotImplementedError]

    # Endpoint to test if server comes up
    @app.route("/ping")
    def ping():
        return "PONG"

    @app.errorhandler(Exception)
    def handle_base_exception(e):
        logger.exception(e)
        if config.TESTING:
            response = ErrorResponse(description=str(e))
        else:
            response = ErrorResponse(description="Unhandled error during request")
        return (to_json_response(response), HTTPStatus.INTERNAL_SERVER_ERROR)

    @app.errorhandler(ClientError)
    def handle_not_implementedClientError(e):
        logger.exception(e)
        return (
            to_json_response(ErrorResponse(description=str(e))),
            HTTPStatus.NOT_IMPLEMENTED,
        )

    @app.errorhandler(NotImplementedError)
    def handle_not_implemented(e):
        logger.exception(e)
        return (
            to_json_response(ErrorResponse(description="Not Implemented")),
            HTTPStatus.NOT_IMPLEMENTED,
        )

    @app.cli.command("check-duplicate-certs")
    def check_duplicate_alb_certs_command():
        log_duplicate_alb_cert_metrics()

    @app.cli.command("remove-duplicate-certs")
    def remove_duplicate_alb_certs_command():
        remove_duplicate_alb_certs()

    @app.cli.command("create-dedicated-alb-waf-web-acls")
    def create_dedicated_alb_waf_web_acls_command():
        create_dedicated_alb_waf_web_acls()

    @app.cli.command("associate-dedicated-alb-waf-web-acls")
    def associate_dedicated_alb_waf_web_acls_command():
        associate_dedicated_alb_waf_web_acls()

    @app.cli.command("add-dedicated-alb-tags")
    def add_dedicated_alb_tags_command():
        add_dedicated_alb_tags()

    return app
