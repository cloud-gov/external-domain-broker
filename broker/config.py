"""Flask config class."""
import os

from environs import Env

base_dir = os.path.abspath(os.path.dirname(__file__))
env = Env()


class Config:
    def __init__(self):
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False
        self.TESTING = True
        self.DEBUG = True


class ProductionConfig(Config):
    def __init__(self):
        super().__init__()
        self.TESTING = False
        self.DEBUG = False
        self.SECRET_KEY = env("SECRET_KEY")
        self.BROKER_USERNAME = env("BROKER_USERNAME")
        self.BROKER_PASSWORD = env("BROKER_PASSWORD")
        self.SQLALCHEMY_DATABASE_URI = env("DATABASE_URL")
        self.REDIS_HOST = env("REDIS_HOST")
        self.REDIS_PORT = env.int("REDIS_PORT")
        self.REDIS_PASSWORD = env("REDIS_PASSWORD")
        self.ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"


class UpgradeSchemaConfig(Config):
    """
    I'm used when running flask db upgrade in any environment
    """
    def __init__(self):
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = env("DATABASE_URL")
        self.TESTING = False
        self.DEBUG = False
        self.SECRET_KEY = "NONE"
        self.BROKER_USERNAME = "NONE"
        self.BROKER_PASSWORD = "NONE"
        self.REDIS_HOST = "NONE"
        self.REDIS_PORT = 1234
        self.REDIS_PASSWORD = "NONE"
        self.ACME_DIRECTORY = "NONE"


class StagingConfig(Config):
    def __init__(self):
        super().__init__()
        self.TESTING = False
        self.DEBUG = False
        self.SECRET_KEY = env("SECRET_KEY")
        self.BROKER_USERNAME = env("BROKER_USERNAME")
        self.BROKER_PASSWORD = env("BROKER_PASSWORD")
        self.SQLALCHEMY_DATABASE_URI = env("DATABASE_URL")
        self.REDIS_HOST = env("REDIS_HOST")
        self.REDIS_PORT = env.int("REDIS_PORT")
        self.REDIS_PASSWORD = env("REDIS_PASSWORD")
        self.ACME_DIRECTORY = "https://acme-staging-v02.api.letsencrypt.org/directory"


class DevelopmentConfig(Config):
    def __init__(self):
        super().__init__()
        self.TESTING = False
        self.DEBUG = False
        self.SECRET_KEY = env("SECRET_KEY")
        self.BROKER_USERNAME = env("BROKER_USERNAME")
        self.BROKER_PASSWORD = env("BROKER_PASSWORD")
        self.SQLALCHEMY_DATABASE_URI = env("DATABASE_URL")
        self.REDIS_HOST = env("REDIS_HOST")
        self.REDIS_PORT = env.int("REDIS_PORT")
        self.REDIS_PASSWORD = env("REDIS_PASSWORD")
        self.ACME_DIRECTORY = "https://acme-staging-v02.api.letsencrypt.org/directory"


class LocalDevelopmentConfig(Config):
    def __init__(self):
        super().__init__()
        self.SQLITE_DB_PATH = os.path.join(base_dir, "..", "dev.sqlite")
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
    mapping = {
        "test": TestConfig,
        "local-development": LocalDevelopmentConfig,
        "development": DevelopmentConfig,
        "staging": StagingConfig,
        "upgrade-schema": UpgradeSchemaConfig,
        "production": ProductionConfig,
    }
    return mapping[env("FLASK_ENV")]()
