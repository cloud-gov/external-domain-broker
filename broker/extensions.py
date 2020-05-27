from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from huey import RedisHuey

from broker.config import config_from_env


config = config_from_env()
db = SQLAlchemy()
migrate = Migrate()
huey = RedisHuey(
    host=config.REDIS_HOST, port=config.REDIS_PORT, password=config.REDIS_PASSWORD,
)
