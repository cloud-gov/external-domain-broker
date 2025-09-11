"""Flask config class."""

import re
from typing import Type, Optional

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
        "check-duplicate-certs": CheckDuplicateCertsConfig,
        "local-debugging": LocalDebuggingConfig,
        "remove-duplicate-certs": RemoveDuplicateCertsConfig,
    }


def config_from_env() -> Type["Config"]:
    env = Env()
    print(f'Grabbing config for {env("FLASK_ENV")}')
    return env_mappings()[env("FLASK_ENV")]()


class Config:
    ACME_DIRECTORY: str
    ACME_POLL_TIMEOUT_IN_SECONDS: int
    ALB_IAM_SERVER_CERTIFICATE_PREFIX: str
    ALB_LISTENER_ARNS: list[str]
    ALB_OVERLAP_SLEEP_TIME: int
    ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN: str
    ALLOWED_AWS_MANAGED_CACHE_POLICIES: list[str]
    ALLOWED_AWS_MANAGED_ORIGIN_VIEWER_REQUEST_POLICIES: list[str]
    AWS_COMMERCIAL_ACCESS_KEY_ID: str
    AWS_COMMERCIAL_GLOBAL_REGION: str
    AWS_COMMERCIAL_REGION: str
    AWS_COMMERCIAL_SECRET_ACCESS_KEY: str
    AWS_GOVCLOUD_ACCESS_KEY_ID: str
    AWS_GOVCLOUD_REGION: str
    AWS_GOVCLOUD_SECRET_ACCESS_KEY: str
    AWS_RESOURCE_PREFIX: str
    AWS_POLL_MAX_ATTEMPTS: int
    AWS_POLL_WAIT_TIME_IN_SECONDS: int
    BROKER_PASSWORD: str
    BROKER_USERNAME: str
    CDN_LOG_BUCKET: str
    CDN_WAF_CLOUDWATCH_LOG_GROUP_ARN: str
    CF_API_URL: str
    CLOUDFRONT_HOSTED_ZONE_ID: str
    CLOUDFRONT_IAM_SERVER_CERTIFICATE_PREFIX: str
    DEBUG: bool
    DEFAULT_CLOUDFRONT_ORIGIN: str
    DATABASE_ENCRYPTION_KEY: str
    DEDICATED_ALB_LISTENER_ARN_MAP: dict | list
    DELETE_WEB_ACL_WAIT_RETRY_TIME: int
    DNS_ROOT_DOMAIN: str
    DNS_VERIFICATION_SERVER: str
    DNS_PROPAGATION_SLEEP_TIME: int
    IGNORE_DUPLICATE_DOMAINS: bool
    FLASK_ENV: str
    MAX_CERTS_PER_ALB: int
    REDIS_HOST: str
    REDIS_PASSWORD: str
    REDIS_PORT: int
    REDIS_SSL: bool
    REQUEST_TIMEOUT: int
    ROUTE53_ZONE_ID: str
    SECRET_KEY: str
    SQLALCHEMY_TRACK_MODIFICATIONS: bool
    SECRET_KEY: str
    SMTP_HOST: str
    SMTP_FROM: str
    SMTP_CERT: Optional[str]
    SMTP_USER: Optional[str]
    SMTP_PASS: Optional[str]
    SMTP_PORT: int
    SMTP_TO: str
    SMTP_TLS: bool
    SQLALCHEMY_DATABASE_URI: str
    TESTING: bool
    UAA_BASE_URL: str
    UAA_CLIENT_ID: str
    UAA_CLIENT_SECRET: str
    UAA_TOKEN_URL: str
    WAF_RATE_LIMIT_RULE_GROUP_ARN: str

    def __init__(self):
        self.env = Env()
        self.cfenv = AppEnv()
        self.FLASK_ENV = self.env("FLASK_ENV")
        self.TMPDIR = self.env("TMPDIR", "/app/tmp/")
        # how long we wait for DNS before trying an acme challenge
        self.DNS_PROPAGATION_SLEEP_TIME = self.env.int(
            "DNS_PROPAGATION_SLEEP_TIME", 300
        )
        # how long we wait between updating DNS to point to a new ALB and removing the
        # certificate from an old ALB
        self.ALB_OVERLAP_SLEEP_TIME = self.env.int("ALB_OVERLAP_SLEEP_TIME", 900)
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False
        self.TESTING = True
        self.DEBUG = True
        self.ACME_POLL_TIMEOUT_IN_SECONDS = self.env.int(
            "ACME_POLL_TIMEOUT_IN_SECONDS", 90
        )
        self.AWS_POLL_WAIT_TIME_IN_SECONDS = 60
        self.AWS_POLL_MAX_ATTEMPTS = 10
        self.IGNORE_DUPLICATE_DOMAINS = self.env.bool("IGNORE_DUPLICATE_DOMAINS", False)

        # https://docs.aws.amazon.com/Route53/latest/APIReference/API_AliasTarget.html
        self.CLOUDFRONT_HOSTED_ZONE_ID = "Z2FDTNDATAQYW2"

        # the maximum from AWS is 25, and we alert when we have 20 on a given alb
        self.MAX_CERTS_PER_ALB = 19

        self.AWS_RESOURCE_PREFIX = f"cg-external-domains-{self.FLASK_ENV}"

        # see https://requests.readthedocs.io/en/latest/user/advanced/#timeouts
        self.REQUEST_TIMEOUT = 30

        # see https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html
        # NOTE: The values in the list are not the same as the policy names on the AWS documentation page. These
        # values are the actual policy names as returned by a CloudFront ListCachePolicies request. Since our code
        # will check for allowed policies against the list of names returned by the API, we use the names from the
        # API response instead of the documentation.
        self.ALLOWED_AWS_MANAGED_CACHE_POLICIES = [
            "Managed-CachingDisabled",
            "Managed-CachingOptimized",
            "Managed-CachingOptimizedForUncompressedObjects",
            "UseOriginCacheControlHeaders",
            "UseOriginCacheControlHeaders-QueryStrings",
        ]

        # see https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html
        # NOTE: The values in the list are not the same as the policy names on the AWS documentation page. These
        # values are the actual policy names as returned by a CloudFront ListOriginRequestPolicies request. Since
        # our code will check for allowed policies against the list of names returned by the API, we use the names
        # from the API response instead of the documentation.
        self.ALLOWED_AWS_MANAGED_ORIGIN_VIEWER_REQUEST_POLICIES = [
            "Managed-AllViewer",
            "Managed-AllViewerAndCloudFrontHeaders-2022-06",
        ]

        self.ACME_DIRECTORY = "NONE"
        self.ALB_IAM_SERVER_CERTIFICATE_PREFIX = "NONE"
        self.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN = "None"
        self.ALB_LISTENER_ARNS = []
        self.AWS_COMMERCIAL_ACCESS_KEY_ID = "NONE"
        self.AWS_COMMERCIAL_GLOBAL_REGION = "NONE"
        self.AWS_COMMERCIAL_REGION = "NONE"
        self.AWS_COMMERCIAL_SECRET_ACCESS_KEY = "NONE"
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = "NONE"
        self.AWS_GOVCLOUD_REGION = "NONE"
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = "NONE"
        self.BROKER_PASSWORD = "NONE"
        self.BROKER_USERNAME = "NONE"
        self.CDN_LOG_BUCKET = "NONE"
        self.CDN_WAF_CLOUDWATCH_LOG_GROUP_ARN = "NONE"
        self.CF_API_URL = "NONE"
        self.CLOUDFRONT_IAM_SERVER_CERTIFICATE_PREFIX = "NONE"
        self.DATABASE_ENCRYPTION_KEY = "NONE"
        self.DEDICATED_ALB_LISTENER_ARN_MAP = {}
        self.DELETE_WEB_ACL_WAIT_RETRY_TIME = 0
        self.DEFAULT_CLOUDFRONT_ORIGIN = "NONE"
        self.DNS_ROOT_DOMAIN = "NONE"
        self.DNS_VERIFICATION_SERVER = "8.8.8.8:53"
        self.REDIS_HOST = "NONE"
        self.REDIS_PASSWORD = "NONE"
        self.REDIS_PORT = 1234
        self.REDIS_SSL = False
        self.ROUTE53_ZONE_ID = "NONE"
        self.SECRET_KEY = "NONE"
        self.SMTP_HOST = "NONE"
        self.SMTP_FROM = "NONE"
        self.SMTP_CERT = None
        self.SMTP_USER = None
        self.SMTP_PASS = None
        self.SMTP_PORT = 1234
        self.SMTP_TO = "NONE"
        self.SMTP_TLS = True
        self.SQLALCHEMY_DATABASE_URI = "NONE"
        self.WAF_RATE_LIMIT_RULE_GROUP_ARN = "NONE"
        self.UAA_BASE_URL = "NONE"
        self.UAA_CLIENT_ID = "NONE"
        self.UAA_CLIENT_SECRET = "NONE"
        self.UAA_TOKEN_URL = "NONE"


class AppConfig(Config):
    """Base class for apps running in Cloud Foundry"""

    def __init__(self):
        super().__init__()
        self.TESTING = False
        self.DEBUG = False
        self.SECRET_KEY = self.env("SECRET_KEY")
        self.BROKER_USERNAME = self.env("BROKER_USERNAME")
        self.BROKER_PASSWORD = self.env("BROKER_PASSWORD")
        self.SQLALCHEMY_DATABASE_URI = normalize_db_url(self.env("DATABASE_URL"))
        self.ALB_LISTENER_ARNS = self.env.list("ALB_LISTENER_ARNS")
        self.ALB_LISTENER_ARNS = list(set(self.ALB_LISTENER_ARNS))
        self.DEDICATED_ALB_LISTENER_ARN_MAP = self.env.json(
            "DEDICATED_ALB_LISTENER_ARN_MAP"
        )

        self.AWS_COMMERCIAL_REGION = self.env("AWS_COMMERCIAL_REGION")
        self.AWS_COMMERCIAL_GLOBAL_REGION = self.env("AWS_COMMERCIAL_GLOBAL_REGION")
        self.AWS_COMMERCIAL_ACCESS_KEY_ID = self.env("AWS_COMMERCIAL_ACCESS_KEY_ID")
        self.AWS_COMMERCIAL_SECRET_ACCESS_KEY = self.env(
            "AWS_COMMERCIAL_SECRET_ACCESS_KEY"
        )
        self.AWS_GOVCLOUD_REGION = self.env("AWS_GOVCLOUD_REGION")
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = self.env("AWS_GOVCLOUD_ACCESS_KEY_ID")
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = self.env("AWS_GOVCLOUD_SECRET_ACCESS_KEY")
        self.CDN_LOG_BUCKET = self.env("CDN_LOG_BUCKET")

        redis = self.cfenv.get_service(label=re.compile("redis.*"))

        if not redis:
            raise MissingRedisError

        self.REDIS_HOST = redis.credentials["host"]
        self.REDIS_PORT = redis.credentials["port"]
        self.REDIS_PASSWORD = redis.credentials["password"]
        self.ROUTE53_ZONE_ID = self.env("ROUTE53_ZONE_ID")
        self.DNS_ROOT_DOMAIN = self.env("DNS_ROOT_DOMAIN")
        self.DNS_VERIFICATION_SERVER = "8.8.8.8:53"
        self.CLOUDFRONT_IAM_SERVER_CERTIFICATE_PREFIX = (
            f"/cloudfront/external-domains-{self.FLASK_ENV}/"
        )
        self.ALB_IAM_SERVER_CERTIFICATE_PREFIX = (
            f"/alb/external-domains-{self.FLASK_ENV}/"
        )
        self.DATABASE_ENCRYPTION_KEY = self.env("DATABASE_ENCRYPTION_KEY")
        self.DEFAULT_CLOUDFRONT_ORIGIN = self.env("DEFAULT_CLOUDFRONT_ORIGIN")
        self.REDIS_SSL = True

        self.SMTP_HOST = self.env("SMTP_HOST")
        self.SMTP_FROM = self.env("SMTP_FROM")
        self.SMTP_CERT = self.env("SMTP_CERT")
        self.SMTP_USER = self.env("SMTP_USER")
        self.SMTP_PASS = self.env("SMTP_PASS")
        self.SMTP_PORT = self.env.int("SMTP_PORT")
        self.SMTP_TO = self.env("SMTP_TO")
        self.SMTP_TLS = True
        self.IAM_CERTIFICATE_PROPAGATION_TIME = 30

        self.WAF_RATE_LIMIT_RULE_GROUP_ARN = self.env("WAF_RATE_LIMIT_RULE_GROUP_ARN")
        # in seconds
        self.DELETE_WEB_ACL_WAIT_RETRY_TIME = 5

        self.CF_API_URL = self.env("CF_API_URL")

        self.UAA_BASE_URL = self.env("UAA_BASE_URL")
        if self.UAA_BASE_URL[-1] != "/":
            self.UAA_BASE_URL = f"{self.UAA_BASE_URL}/"
        self.UAA_TOKEN_URL = f"{self.UAA_BASE_URL}oauth/token"

        self.UAA_CLIENT_ID = self.env("UAA_CLIENT_ID")
        self.UAA_CLIENT_SECRET = self.env("UAA_CLIENT_SECRET")

        self.CDN_WAF_CLOUDWATCH_LOG_GROUP_ARN = self.env(
            "CDN_WAF_CLOUDWATCH_LOG_GROUP_ARN"
        )
        self.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN = self.env(
            "ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN"
        )


class ProductionConfig(AppConfig):
    def __init__(self):
        super().__init__()
        self.ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"


class StagingConfig(AppConfig):
    def __init__(self):
        super().__init__()
        self.ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"


class DevelopmentConfig(AppConfig):
    def __init__(self):
        super().__init__()
        self.ACME_DIRECTORY = "https://acme-staging-v02.api.letsencrypt.org/directory"


class UpgradeSchemaConfig(Config):
    """I'm used when running flask db upgrade in any self.environment"""

    def __init__(self):
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = normalize_db_url(self.env("DATABASE_URL"))
        self.TESTING = False
        self.DEBUG = False
        self.SECRET_KEY = "NONE"
        self.BROKER_USERNAME = "NONE"
        self.BROKER_PASSWORD = "NONE"
        self.DATABASE_ENCRYPTION_KEY = self.env("DATABASE_ENCRYPTION_KEY")
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
        self.AWS_COMMERCIAL_GLOBAL_REGION = "NONE"
        self.AWS_GOVCLOUD_REGION = "NONE"
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = "NONE"
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = "NONE"
        self.ALB_LISTENER_ARNS = []
        self.DEDICATED_ALB_LISTENER_ARN_MAP = {}
        self.WAF_RATE_LIMIT_RULE_GROUP_ARN = "NONE"


class CheckDuplicateCertsConfig(UpgradeSchemaConfig):
    """I'm used when running flask check-duplicate-certs in any self.environment"""

    def __init__(self):
        super().__init__()
        self.ALB_LISTENER_ARNS = self.env.list("ALB_LISTENER_ARNS")
        self.ALB_LISTENER_ARNS = list(set(self.ALB_LISTENER_ARNS))


class RemoveDuplicateCertsConfig(CheckDuplicateCertsConfig):
    """I'm used when running flask remove-duplicate-certs in any self.environment"""

    def __init__(self):
        super().__init__()
        self.AWS_GOVCLOUD_REGION = self.env("AWS_GOVCLOUD_REGION")
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = self.env("AWS_GOVCLOUD_ACCESS_KEY_ID")
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = self.env("AWS_GOVCLOUD_SECRET_ACCESS_KEY")


class DockerConfig(Config):
    """Base class for running in the local dev docker image"""

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
        self.DEDICATED_ALB_LISTENER_ARN_MAP = {"dedicated-listener-arn-0": "org1"}
        self.CLOUDFRONT_IAM_SERVER_CERTIFICATE_PREFIX = (
            "/cloudfront/external-domains-test/"
        )
        self.ALB_IAM_SERVER_CERTIFICATE_PREFIX = "/alb/external-domains-test/"
        self.REDIS_SSL = False
        self.ALB_LISTENER_ARNS = ["listener-arn-0", "listener-arn-1"]
        self.AWS_COMMERCIAL_REGION = "us-west-1"
        self.AWS_COMMERCIAL_ACCESS_KEY_ID = "COMMERCIAL_FAKE_KEY_ID"
        self.AWS_COMMERCIAL_SECRET_ACCESS_KEY = "COMMERCIAL_FAKE_ACCESS_KEY"
        self.AWS_COMMERCIAL_GLOBAL_REGION = "global-1"
        self.AWS_GOVCLOUD_REGION = "us-gov-west-1"
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = "GOVCLOUD_FAKE_KEY_ID"
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = "GOVCLOUD_FAKE_ACCESS_KEY"
        self.CDN_LOG_BUCKET = "mybucket.s3.amazonaws.com"

        self.SMTP_HOST = "localhost"
        self.SMTP_PORT = 1025

        # when testing, this goes to a fake smtp server that only prints stuff,
        # so example.com is a safe host
        self.SMTP_TO = "doesnt-matter@example.com"
        self.SMTP_FROM = "no-reply@example.com"
        self.SMTP_TLS = False
        self.SMTP_USER = None
        self.SMTP_PASS = None

        self.WAF_RATE_LIMIT_RULE_GROUP_ARN = "rate-limit-rule-group-fake-arn"
        self.CDN_WAF_CLOUDWATCH_LOG_GROUP_ARN = "fake-waf-cloudwatch-log-grou-arn"
        self.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN = "fake-alb-waf-cloudwatch-log-group-arn"

        self.CF_API_URL = "http://mock.cf/"
        self.UAA_TOKEN_URL = "http://mock.uaa/token"
        self.UAA_CLIENT_ID = "EXAMPLE"
        self.UAA_CLIENT_SECRET = "example"


class LocalDevelopmentConfig(DockerConfig):
    def __init__(self):
        super().__init__()


class LocalDebuggingConfig(DockerConfig):
    def __init__(self):
        super().__init__()
        self.SQLALCHEMY_DATABASE_URI = (
            f"postgresql://:{self.env('PGPASSWORD', '')}@localhost/local-development"
        )


class TestConfig(DockerConfig):
    def __init__(self):
        super().__init__()
        self.DNS_PROPAGATION_SLEEP_TIME = 0
        self.ALB_OVERLAP_SLEEP_TIME = 0
        self.ACME_POLL_TIMEOUT_IN_SECONDS = 10
        self.AWS_POLL_WAIT_TIME_IN_SECONDS = 0
        self.AWS_POLL_MAX_ATTEMPTS = 10
        # if you need to see what sqlalchemy is doing
        # self.SQLALCHEMY_ECHO = True
        self.IAM_CERTIFICATE_PROPAGATION_TIME = 0
        # in seconds
        self.DELETE_WEB_ACL_WAIT_RETRY_TIME = 0


class MissingRedisError(RuntimeError):
    def __init__(self):
        super().__init__("Cannot find redis in VCAP_SERVICES")


def normalize_db_url(url):
    # sqlalchemy no longer lets us use postgres://
    # it requires postgresql://
    if url.split(":")[0] == "postgres":
        url = url.replace("postgres:", "postgresql:", 1)
    return url
