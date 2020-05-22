import json

import pytest

from broker.config import config_from_env


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
        "redis32": [
            {
                "credentials": {
                    "hostname": "my-redis-hostname",
                    "password": "my-redis-password",
                    "port": "my-redis-port",
                    "ports": {"6379/tcp": "my-redis-port-tuple"},
                    "uri": "my-redis-uri",
                },
                "instance_name": "my-app-name-redis",
                "label": "redis32",
                "name": "my-app-name-redis",
                "plan": "standard-ha",
                "tags": ["redis32", "redis"],
            }
        ],
    }

    return json.dumps(data)


@pytest.fixture()
def mocked_env(monkeypatch, vcap_application, vcap_services):
    monkeypatch.setenv("SECRET_KEY", "None")
    monkeypatch.setenv("BROKER_USERNAME", "None")
    monkeypatch.setenv("BROKER_PASSWORD", "None")
    monkeypatch.setenv("DATABASE_URL", "None")
    monkeypatch.setenv("ROUTE53_ZONE_ID", "None")
    monkeypatch.setenv("DNS_ROOT_DOMAIN", "None")
    monkeypatch.setenv("DNS_VERIFICATION_SERVER", "127.0.0.1:53")
    monkeypatch.setenv("VCAP_APPLICATION", vcap_application)
    monkeypatch.setenv("VCAP_SERVICES", vcap_services)


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_parses_VCAP_SERVICES(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert config.REDIS_HOST == "my-redis-hostname"
    assert config.REDIS_PORT == "my-redis-port"
    assert config.REDIS_PASSWORD == "my-redis-password"


@pytest.mark.parametrize("env", ["staging", "development"])
def test_config_uses_staging_acme_url(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert (
        config.ACME_DIRECTORY
        == "https://acme-staging-v02.api.letsencrypt.org/directory"
    )


@pytest.mark.parametrize("env", ["production"])
def test_config_uses_prod_acme_url(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert config.ACME_DIRECTORY == "https://acme-v02.api.letsencrypt.org/directory"


@pytest.mark.parametrize("env", ["production", "staging", "development"])
def test_config_uses_right_iam_prefix(env, monkeypatch, mocked_env):
    monkeypatch.setenv("FLASK_ENV", env)

    config = config_from_env()

    assert (
        config.IAM_SERVER_CERTIFICATE_PREFIX
        == f"/cloudfront/external-service-broker/{env}"
    )
