"""Flask config class."""
import os
import re
from typing import Type

from cfenv import AppEnv
from environs import Env


def env_mappings():
    return {
        "test": TestConfig,
        "local-development": LocalDevelopmentConfig,
        "development": DevelopmentConfig,
        "staging": StagingConfig,
        "production": ProductionConfig,
        "upgrade-schema": UpgradeSchemaConfig,
    }


def config_from_env() -> Type["Config"]:
    env = Env()
    print(f'Grabbing config for {env("FLASK_ENV")}')
    return env_mappings()[env("FLASK_ENV")]()


class Config:
    def __init__(self):
        self.env = Env()
        self.cfenv = AppEnv()
        self.FLASK_ENV = self.env("FLASK_ENV")
        self.TMPDIR = self.env("TMPDIR", "/app/tmp/")
        self.DNS_PROPAGATION_SLEEP_TIME = self.env("DNS_PROPAGATION_SLEEP_TIME", "300")
        self.CLOUDFRONT_PROPAGATION_SLEEP_TIME = 60  # Seconds
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False
        self.TESTING = True
        self.DEBUG = True
        self.ACME_POLL_TIMEOUT_IN_SECONDS = self.env("ACME_POLL_TIMEOUT_IN_SECONDS", 90)
        self.AWS_POLL_WAIT_TIME_IN_SECONDS = 60
        self.AWS_POLL_MAX_ATTEMPTS = 120

        # https://docs.aws.amazon.com/Route53/latest/APIReference/API_AliasTarget.html
        self.CLOUDFRONT_HOSTED_ZONE_ID = "Z2FDTNDATAQYW2"


class AppConfig(Config):
    """ Base class for apps running in Cloud Foundry """

    def __init__(self):
        super().__init__()
        self.TESTING = False
        self.DEBUG = False
        self.SECRET_KEY = self.env("SECRET_KEY")
        self.BROKER_USERNAME = self.env("BROKER_USERNAME")
        self.BROKER_PASSWORD = self.env("BROKER_PASSWORD")
        self.SQLALCHEMY_DATABASE_URI = self.env("DATABASE_URL")
        self.ALB_ARNS = self.env.list("ALB_ARNS")
        self.ALB_ARNS = list(set(self.ALB_ARNS))
        self.AWS_COMMERCIAL_REGION = self.env("AWS_COMMERCIAL_REGION")
        self.AWS_COMMERCIAL_ACCESS_KEY_ID = self.env("AWS_COMMERCIAL_ACCESS_KEY_ID")
        self.AWS_COMMERCIAL_SECRET_ACCESS_KEY = self.env(
            "AWS_COMMERCIAL_SECRET_ACCESS_KEY"
        )
        self.AWS_GOVCLOUD_REGION = self.env("AWS_GOVCLOUD_REGION")
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = self.env("AWS_GOVCLOUD_ACCESS_KEY_ID")
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = self.env("AWS_GOVCLOUD_SECRET_ACCESS_KEY")

        redis = self.cfenv.get_service(label=re.compile("redis.*"))

        if not redis:
            raise MissingRedisError

        self.REDIS_HOST = redis.credentials["host"]
        self.REDIS_PORT = redis.credentials["port"]
        self.REDIS_PASSWORD = redis.credentials["password"]
        self.ROUTE53_ZONE_ID = self.env("ROUTE53_ZONE_ID")
        self.DNS_ROOT_DOMAIN = self.env("DNS_ROOT_DOMAIN")
        self.DNS_VERIFICATION_SERVER = "8.8.8.8:53"
        self.IAM_SERVER_CERTIFICATE_PREFIX = (
            f"/cloudfront/external-domains-{self.FLASK_ENV}/"
        )
        self.DATABASE_ENCRYPTION_KEY = self.env("DATABASE_ENCRYPTION_KEY")
        self.DEFAULT_CLOUDFRONT_ORIGIN = self.env("DEFAULT_CLOUDFRONT_ORIGIN")
        self.REDIS_SSL = True


class ProductionConfig(AppConfig):
    def __init__(self):
        self.ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
        super().__init__()


class StagingConfig(AppConfig):
    def __init__(self):
        self.ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
        super().__init__()


class DevelopmentConfig(AppConfig):
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
        self.DATABASE_ENCRYPTION_KEY = "NONE"
        self.REDIS_HOST = "NONE"
        self.REDIS_PORT = 1234
        self.REDIS_PASSWORD = "NONE"
        self.ACME_DIRECTORY = "NONE"
        self.ROUTE53_ZONE_ID = "NONE"
        self.DNS_ROOT_DOMAIN = "NONE"
        self.DNS_VERIFICATION_SERVER = "8.8.8.8:53"
        self.REDIS_SSL = False
        self.AWS_COMMERCIAL_REGION = "NONE"
        self.AWS_COMMERCIAL_ACCESS_KEY_ID = "NONE"
        self.AWS_COMMERCIAL_SECRET_ACCESS_KEY = "NONE"
        self.AWS_GOVCLOUD_REGION = "NONE"
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = "NONE"
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = "NONE"


class DockerConfig(Config):
    """ Base class for running in the local dev docker image """

    def __init__(self):
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = f"postgresql://localhost/{self.FLASK_ENV}"
        self.REDIS_HOST = "localhost"
        self.REDIS_PORT = 6379
        self.REDIS_PASSWORD = "sekrit"
        self.SECRET_KEY = "Sekrit Key"
        self.BROKER_USERNAME = "broker"
        self.BROKER_PASSWORD = "sekrit"
        self.ACME_DIRECTORY = "https://localhost:14000/dir"
        self.DNS_VERIFICATION_SERVER = "127.0.0.1:8053"
        self.ROUTE53_ZONE_ID = "TestZoneID"
        self.DNS_ROOT_DOMAIN = "domains.cloud.test"
        self.DATABASE_ENCRYPTION_KEY = "Local Dev Encrytpion Key"
        self.DEFAULT_CLOUDFRONT_ORIGIN = "cloud.local"
        self.IAM_SERVER_CERTIFICATE_PREFIX = "/cloudfront/external-domains-test/"
        self.REDIS_SSL = False
        self.ALB_ARNS = ["alb-arn-0", "alb-arn-1"]
        self.AWS_COMMERCIAL_REGION = "us-west-1"
        self.AWS_COMMERCIAL_ACCESS_KEY_ID = "COMMERCIAL_FAKE_KEY_ID"
        self.AWS_COMMERCIAL_SECRET_ACCESS_KEY = "COMMERCIAL_FAKE_ACCESS_KEY"
        self.AWS_GOVCLOUD_REGION = "us-gov-west-1"
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = "GOVCLOUD_FAKE_KEY_ID"
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = "GOVCLOUD_FAKE_ACCESS_KEY"


class LocalDevelopmentConfig(DockerConfig):
    def __init__(self):
        super().__init__()


class TestConfig(DockerConfig):
    def __init__(self):
        super().__init__()
        self.DNS_PROPAGATION_SLEEP_TIME = 0
        self.CLOUDFRONT_PROPAGATION_SLEEP_TIME = 0
        self.ACME_POLL_TIMEOUT_IN_SECONDS = 10
        self.AWS_POLL_WAIT_TIME_IN_SECONDS = 1
        self.AWS_POLL_MAX_ATTEMPTS = 10


class MissingRedisError(RuntimeError):
    def __init__(self):
        super().__init__("Cannot find redis in VCAP_SERVICES")
