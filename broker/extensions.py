from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from broker.config import config_from_env
from broker.tasks.shield import ShieldProtections

config = config_from_env()
db = SQLAlchemy(disable_autonaming=True)
migrate = Migrate()

# Initialize here so that the class and its dictionary of mapped protections are
# kept in memory for use by tasks
shield_protections = ShieldProtections()
