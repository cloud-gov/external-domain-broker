import logging

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from openbrokerapi.api import BrokerCredentials

from . import log_util
from .config import Config

log_util.configure(logging.root, log_level="INFO")
logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    # We need to import models, even though it's unused, in order to enable
    # `flask db migrate`
    from broker import models  # noqa: F401

    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    credentials = BrokerCredentials(
        app.config["BROKER_USERNAME"], app.config["BROKER_PASSWORD"]
    )

    from .broker import create_broker_blueprint

    app.register_blueprint(create_broker_blueprint(credentials))

    # Endpoint to test if server comes up
    @app.route("/ping")
    def ping():
        return "PONG"

    return app
