import logging
import os

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from openbrokerapi.api import BrokerCredentials

from . import log_util
from .broker import create_broker_blueprint

# Configure logging
# You can overwrite the log_level by setting LOG_LEVEL in the environment
log_util.configure(logging.root, log_level="INFO")
logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    # We need to import models, even though it's unused, in order to enable
    # `flask db migrate`
    from broker import models  # noqa: F401

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev"
    app.config["DATABASE"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["DATABASE"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Read config from env
    broker_username = os.getenv("BROKER_USERNAME")
    broker_password = os.getenv("BROKER_PASSWORD")

    # Setup auth if env vars are set
    if broker_username and broker_password:
        credentials = BrokerCredentials(broker_username, broker_password)
    else:
        credentials = None

    app.register_blueprint(create_broker_blueprint(credentials))

    # Endpoint to test if server comes up
    @app.route("/ping")
    def ping():
        return "PONG"

    return app
