import json
import uuid

import pytest

from broker.config import config_from_env, env_mappings


@pytest.fixture()
def vcap_application():
    data = {
        "application_id": "my-app-id",
        "application_name": "my-app-name",
        "application_uris": ["my-app-uri"],
        "application_version": "my-app-version",
        "cf_api": "cf-api",
        "name": "my-app-name",
        "organization_name": "my-org-name",
        "space_name": "my-space-name",
        "process_type": "web",
        "uris": ["my-app-uri"],
        "version": "my-app-version",
    }

    return json.dumps(data)


@pytest.fixture()
def vcap_services():
    data = {
        "aws-rds": [
            {
                "credentials": {
                    "db_name": "my-db-name",
                    "host": "my-db-host",
                    "password": "my-db-password",
                    "port": "my-db-port",
                    "uri": "my-db-uri",
                    "username": "my-db-username",
                },
                "instance_name": "my-app-name-psql",
                "label": "aws-rds",
                "name": "my-app-name-psql",
                "plan": "medium-psql",
                "tags": ["database", "RDS"],
            }
        ],
        "redis": [
            {
                "credentials": {
                    "host": "my-redis-hostname",
                    "password": "my-redis-password",
                    "port": "my-redis-port",
                    "ports": {"6379/tcp": "my-redis-port-tuple"},
                    "uri": "my-redis-uri",
                },
                "instance_name": "my-app-name-redis",
                "label": "redis",
                "name": "my-app-name-redis",
                "plan": "standard-ha",
                "tags": ["redis", "Elasticache"],
            }
        ],
    }

    return json.dumps(data)


@pytest.fixture
def uaa_client_id():
    return str(uuid.uuid4())


@pytest.fixture
def uaa_client_secret():
    return str(uuid.uuid4())


@pytest.fixture()
def mocked_env(
    monkeypatch, vcap_application, vcap_services, uaa_client_id, uaa_client_secret
):
    monkeypatch.setenv("SECRET_KEY", "None")
    monkeypatch.setenv("BROKER_USERNAME", "None")
    monkeypatch.setenv("BROKER_PASSWORD", "None")
    monkeypatch.setenv("DATABASE_URL", "None")
    monkeypatch.setenv("DATABASE_ENCRYPTION_KEY", "None")
    monkeypatch.setenv("ROUTE53_ZONE_ID", "None")
    monkeypatch.setenv("DNS_ROOT_DOMAIN", "None")
    monkeypatch.setenv("DNS_VERIFICATION_SERVER", "127.0.0.1:53")
    monkeypatch.setenv("VCAP_APPLICATION", vcap_application)
    monkeypatch.setenv("VCAP_SERVICES", vcap_services)
    monkeypatch.setenv("DEFAULT_CLOUDFRONT_ORIGIN", "None")
    # note - we're using the same listener arn twice - this allows us to test deduplication
    monkeypatch.setenv(
        "ALB_LISTENER_ARNS",
        "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/my-load-balancer/1234567890123456,arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/my-load-balancer/1234567890123456",
    )
    monkeypatch.setenv(
        "DEDICATED_ALB_LISTENER_ARN_MAP",
        '{ "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/my-other-load-balancer/1234567890123456": "org1", "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/my-other-load-balancer/7891011121314": "org2" }',
    )
    monkeypatch.setenv("AWS_COMMERCIAL_REGION", "us-west-1")
    monkeypatch.setenv("AWS_COMMERCIAL_GLOBAL_REGION", "global-1")
    monkeypatch.setenv("AWS_COMMERCIAL_ACCESS_KEY_ID", "ASIAFAKEKEY")
    monkeypatch.setenv("AWS_COMMERCIAL_SECRET_ACCESS_KEY", "THIS_IS_A_FAKE_ACCESS_KEY")
    monkeypatch.setenv("AWS_GOVCLOUD_REGION", "us-west-1")
    monkeypatch.setenv("AWS_GOVCLOUD_ACCESS_KEY_ID", "ASIAFAKEKEY")
    monkeypatch.setenv("AWS_GOVCLOUD_SECRET_ACCESS_KEY", "THIS_IS_A_FAKE_ACCESS_KEY")
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "1025")
    monkeypatch.setenv("SMTP_USER", "my-user@example.com")
    monkeypatch.setenv("SMTP_PASS", "this-password-is-invalid")
    monkeypatch.setenv("SMTP_FROM", "no-reply@example.com")
    monkeypatch.setenv("SMTP_TO", "alerts@example.com")
    monkeypatch.setenv("SMTP_CERT", "A_REAL_CERT_WOULD_BE_LONGER_THAN_THIS")
    monkeypatch.setenv("CDN_LOG_BUCKET", "my-bucket.s3.amazonaws.com")
    monkeypatch.setenv("WAF_RATE_LIMIT_RULE_GROUP_ARN", "fake-rate-limit-group-arn")
    monkeypatch.setenv("CF_API_URL", "mock://cf")
    monkeypatch.setenv("UAA_BASE_URL", "mock://uaa")
    monkeypatch.setenv("UAA_CLIENT_ID", uaa_client_id)
    monkeypatch.setenv("UAA_CLIENT_SECRET", uaa_client_secret)
    monkeypatch.setenv(
        "CDN_WAF_CLOUDWATCH_LOG_GROUP_ARN", "fake-waf-cloudwatch-log-group-arn"
    )


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_parses_VCAP_SERVICES(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert config.REDIS_HOST == "my-redis-hostname"
    assert config.REDIS_PORT == "my-redis-port"
    assert config.REDIS_PASSWORD == "my-redis-password"


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_gets_cf_origin_from_env(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)
    monkeypatch.setenv("DEFAULT_CLOUDFRONT_ORIGIN", "foo")

    config = config_from_env()

    assert config.DEFAULT_CLOUDFRONT_ORIGIN == "foo"


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_gets_log_bucket_from_env(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)
    monkeypatch.setenv("CDN_LOG_BUCKET", "foo")

    config = config_from_env()

    assert config.CDN_LOG_BUCKET == "foo"


@pytest.mark.parametrize("env", ["development"])
def test_config_uses_staging_acme_url(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert (
        config.ACME_DIRECTORY
        == "https://acme-staging-v02.api.letsencrypt.org/directory"
    )


@pytest.mark.parametrize("env", ["staging", "production"])
def test_config_uses_prod_acme_url(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert config.ACME_DIRECTORY == "https://acme-v02.api.letsencrypt.org/directory"


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_uses_right_iam_prefix(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert (
        config.CLOUDFRONT_IAM_SERVER_CERTIFICATE_PREFIX
        == f"/cloudfront/external-domains-{env}/"
    )
    assert config.ALB_IAM_SERVER_CERTIFICATE_PREFIX == f"/alb/external-domains-{env}/"


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_sets_smtp_variables(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert config.SMTP_FROM == "no-reply@example.com"
    assert config.SMTP_USER == "my-user@example.com"
    assert config.SMTP_PASS == "this-password-is-invalid"
    assert config.SMTP_HOST == "127.0.0.1"
    assert config.SMTP_PORT == 1025
    assert config.SMTP_CERT == "A_REAL_CERT_WOULD_BE_LONGER_THAN_THIS"
    assert config.SMTP_TO == "alerts@example.com"


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_provides_alb_arns_deduplicated(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    # we have the same arn twice in the fixture, so we expect to see just one here
    assert type(config.ALB_LISTENER_ARNS) == list
    assert config.ALB_LISTENER_ARNS == [
        "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/my-load-balancer/1234567890123456"
    ]


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_provides_dedicated_alb_arns_deduplicated(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert type(config.DEDICATED_ALB_LISTENER_ARN_MAP) == dict
    assert config.DEDICATED_ALB_LISTENER_ARN_MAP == dict(
        {
            "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/my-other-load-balancer/1234567890123456": "org1",
            "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/my-other-load-balancer/7891011121314": "org2",
        }
    )


@pytest.mark.parametrize("env", env_mappings().keys())
def test_config_doesnt_explode(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert env == config.FLASK_ENV


@pytest.mark.parametrize("env", ["production", "staging", "development"])
@pytest.mark.parametrize("dburl_in", ["postgresql://mydb", "postgres://mydb"])
def test_config_fixes_db_uri(env, monkeypatch, mocked_env, dburl_in):
    monkeypatch.setenv("FLASK_ENV", env)
    monkeypatch.setenv("DATABASE_URL", dburl_in)

    config = config_from_env()

    assert config.SQLALCHEMY_DATABASE_URI == "postgresql://mydb"


@pytest.mark.parametrize("env", env_mappings().keys())
def test_config_sets_ignore_duplicates_false_by_default(env, monkeypatch, mocked_env):

    config = config_from_env()

    assert not config.IGNORE_DUPLICATE_DOMAINS


@pytest.mark.parametrize("env", env_mappings().keys())
def test_config_sets_ignore_duplicates_false_by_default(env, monkeypatch, mocked_env):
    monkeypatch.setenv("IGNORE_DUPLICATE_DOMAINS", "true")

    config = config_from_env()

    assert config.IGNORE_DUPLICATE_DOMAINS


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_provides_max_alb_uses(env, monkeypatch, mocked_env):
    config = config_from_env()

    assert isinstance(config.MAX_CERTS_PER_ALB, int)


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_sets_waf_rate_limit_rule_group_arn(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert config.WAF_RATE_LIMIT_RULE_GROUP_ARN == "fake-rate-limit-group-arn"


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_sets_cf_vars(
    env, monkeypatch, mocked_env, uaa_client_id, uaa_client_secret
):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert config.CF_API_URL == "mock://cf"
    assert config.UAA_BASE_URL == "mock://uaa/"
    assert config.UAA_TOKEN_URL == "mock://uaa/oauth/token"
    assert config.UAA_CLIENT_ID == uaa_client_id
    assert config.UAA_CLIENT_SECRET == uaa_client_secret
