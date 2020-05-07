"""Flask config class."""
import os
import re

from cfenv import AppEnv
from environs import Env

base_dir = os.path.abspath(os.path.dirname(__file__))


class MissingNameError(RuntimeError):
    def __init__(self):
        env = Env()
        super().__init__(
            f"Can't find name in VCAP_APPLICATION: {env('VCAP_APPLICATION')}"
        )


class MissingRedisError(RuntimeError):
    def __init__(self):
        env = Env()
        super().__init__(f"Cannot find redis in VCAP_SERVICES: {env('VCAP_SERVICES')}")


class Config:
    def __init__(self):
        self.env = Env()
        self.cfenv = AppEnv()
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False
        self.TESTING = True
        self.DEBUG = True


class LiveConfig(Config):
    """
    Base class for apps running in Cloud Foundry
    """

    def __init__(self):
        super().__init__()
        self.TESTING = False
        self.DEBUG = False
        self.SECRET_KEY = self.env("SECRET_KEY")
        self.BROKER_USERNAME = self.env("BROKER_USERNAME")
        self.BROKER_PASSWORD = self.env("BROKER_PASSWORD")
        self.SQLALCHEMY_DATABASE_URI = self.env("DATABASE_URL")

        redis = self.cfenv.get_service(label=re.compile("redis.*"))
        if not redis:
            raise MissingRedisError

        self.REDIS_HOST = redis.credentials["hostname"]
        self.REDIS_PORT = redis.credentials["port"]
        self.REDIS_PASSWORD = redis.credentials["password"]


class ProductionConfig(LiveConfig):
    def __init__(self):
        super().__init__()
        self.ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"


class StagingConfig(LiveConfig):
    def __init__(self):
        super().__init__()
        self.ACME_DIRECTORY = "https://acme-staging-v02.api.letsencrypt.org/directory"


class DevelopmentConfig(LiveConfig):
    def __init__(self):
        super().__init__()
        self.ACME_DIRECTORY = "https://acme-staging-v02.api.letsencrypt.org/directory"


class UpgradeSchemaConfig(Config):
    """
    I'm used when running flask db upgrade in any self.environment
    """

    def __init__(self):
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = self.env("DATABASE_URL")
        self.TESTING = False
        self.DEBUG = False
        self.SECRET_KEY = "NONE"
        self.BROKER_USERNAME = "NONE"
        self.BROKER_PASSWORD = "NONE"
        self.REDIS_HOST = "NONE"
        self.REDIS_PORT = 1234
        self.REDIS_PASSWORD = "NONE"
        self.ACME_DIRECTORY = "NONE"


class LocalDevelopmentConfig(Config):
    def __init__(self):
        super().__init__()
        self.SQLITE_DB_PATH = os.path.join(base_dir, "..", "tmp", "dev.sqlite")
        self.SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.SQLITE_DB_PATH
        self.REDIS_HOST = "localhost"
        self.REDIS_PORT = 6379
        self.REDIS_PASSWORD = "sekrit"
        self.SECRET_KEY = "Sekrit Key"
        self.BROKER_USERNAME = "broker"
        self.BROKER_PASSWORD = "sekrit"
        self.ACME_DIRECTORY = "https://localhost:14000/dir"  # Local Pebble server.


class TestConfig(Config):
    def __init__(self):
        super().__init__()
        self.SQLITE_DB_PATH = os.path.join(base_dir, "..", "test.sqlite")
        self.SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.SQLITE_DB_PATH
        self.REDIS_HOST = "localhost"
        self.REDIS_PORT = 6379
        self.REDIS_PASSWORD = "sekrit"
        self.SECRET_KEY = "Sekrit Key"
        self.BROKER_USERNAME = "broker"
        self.BROKER_PASSWORD = "sekrit"
        self.ACME_DIRECTORY = "https://localhost:14000/dir"


def config_from_env():
    env = Env()
    mapping = {
        "test": TestConfig,
        "local-development": LocalDevelopmentConfig,
        "development": DevelopmentConfig,
        "staging": StagingConfig,
        "upgrade-schema": UpgradeSchemaConfig,
        "production": ProductionConfig,
    }
    return mapping[env("FLASK_ENV")]()
