import logging
import os

from flask import Flask

from flask_sqlalchemy import SQLAlchemy
from openbrokerapi.api import BrokerCredentials

from . import log_util
from .broker import create_broker_blueprint

# Configure logging
# You can overwrite the log_level by setting LOG_LEVEL in the environment
log_util.configure(logging.root, log_level="INFO")
logger = logging.getLogger(__name__)

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    db_path = os.path.join(app.instance_path, "db.sqlite")
    app.config["SECRET_KEY"] = "dev"
    app.config["DATABASE"] = db_path
    app.config["SQLALCHEMY_DATABASE_URI"] = db_path
    db.init_app(app)

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
