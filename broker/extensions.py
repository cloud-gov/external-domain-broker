from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from broker.aws import cloudfront
from broker.config import config_from_env
from broker.lib.cache_policy_manager import CachePolicyManager

config = config_from_env()
db = SQLAlchemy(disable_autonaming=True)
migrate = Migrate()
cache_policy_manager = CachePolicyManager(cloudfront)
