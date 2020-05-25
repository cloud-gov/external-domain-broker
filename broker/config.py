"""Flask config class."""
import os
import re

from cfenv import AppEnv
from environs import Env
from typing import Type


def config_from_env():
    env = Env()
    return env_mappings()[env("FLASK_ENV")]()


class Config:
    def __init__(self):
        self.env = Env()
        self.cfenv = AppEnv()
        self.FLASK_ENV = self.env("FLASK_ENV")
        self.TMPDIR = self.env("TMPDIR", "/app/tmp/")
        self.DB_ENCRYPTION_KEY = self.env("DB_ENCRYPTION_KEY")
        self.DNS_PROPAGATION_SLEEP_TIME = self.env("DNS_PROPAGATION_SLEEP_TIME", "300")
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False
        self.TESTING = True
        self.DEBUG = True


class LiveConfig(Config):
    """ Base class for apps running in Cloud Foundry """

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
        self.ROUTE53_ZONE_ID = self.env("ROUTE53_ZONE_ID")
        self.DNS_ROOT_DOMAIN = self.env("DNS_ROOT_DOMAIN")
        self.DNS_VERIFICATION_SERVER = "8.8.8.8:53"
        self.IAM_SERVER_CERTIFICATE_PREFIX = (
            f"/cloudfront/external-service-broker/{self.FLASK_ENV}"
        )


class ProductionConfig(LiveConfig):
    def __init__(self):
        self.ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
        super().__init__()


class StagingConfig(LiveConfig):
    def __init__(self):
        self.ACME_DIRECTORY = "https://acme-staging-v02.api.letsencrypt.org/directory"
        super().__init__()


class DevelopmentConfig(LiveConfig):
    def __init__(self):
        self.ACME_DIRECTORY = "https://acme-staging-v02.api.letsencrypt.org/directory"
        super().__init__()


class UpgradeSchemaConfig(Config):
    """ I'm used when running flask db upgrade in any self.environment """

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
        self.ROUTE53_ZONE_ID = "NONE"
        self.DNS_ROOT_DOMAIN = "NONE"
        self.DNS_VERIFICATION_SERVER = "8.8.8.8:53"


class DockerConfig(Config):
    """ Base class for running in the local dev docker image """

    def __init__(self):
        super().__init__()
        self.SQLITE_DB_PATH = os.path.join(self.TMPDIR, self.SQLITE_DB_NAME)
        self.SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.SQLITE_DB_PATH
        self.REDIS_HOST = "localhost"
        self.REDIS_PORT = 6379
        self.REDIS_PASSWORD = "sekrit"
        self.SECRET_KEY = "Sekrit Key"
        self.BROKER_USERNAME = "broker"
        self.BROKER_PASSWORD = "sekrit"
        # Local pebble server.
        self.ACME_DIRECTORY = "https://localhost:14000/dir"
        # Local pebble-challtestsrv server.
        self.DNS_VERIFICATION_SERVER = "127.0.0.1:8053"
        self.ROUTE53_ZONE_ID = "FakeZoneID"
        self.DNS_ROOT_DOMAIN = "domains.cloud.test"


class LocalDevelopmentConfig(DockerConfig):
    def __init__(self):
        self.SQLITE_DB_NAME = "dev.sqlite"
        super().__init__()


class TestConfig(DockerConfig):
    def __init__(self):
        self.SQLITE_DB_NAME = "test.sqlite"
        super().__init__()


class MissingRedisError(RuntimeError):
    def __init__(self):
        super().__init__(f"Cannot find redis in VCAP_SERVICES")


def env_mappings() -> Type[Config]:
    return {
        "test": TestConfig,
        "local-development": LocalDevelopmentConfig,
        "development": DevelopmentConfig,
        "staging": StagingConfig,
        "production": ProductionConfig,
        "upgrade-schema": UpgradeSchemaConfig,
    }


