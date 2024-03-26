from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from broker.config import config_from_env

config = config_from_env()
db = SQLAlchemy(disable_autonaming=True)
migrate = Migrate()
