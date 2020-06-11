import json
from datetime import date, datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import Challenge, Operation, CdnServiceInstance
from tests.lib.factories import CdnServiceInstanceFactory

# The subtests below are "interesting".  Before test_provision_happy_path, we
# had separate tests for each stage in the task pipeline.  But each test would
# have to duplicate much of the previous test.  This was arduous and slow. Now
# we have a single test_provision_happy_path, and many subtest_foo helper
# methods.  This still makes it clear which stage in the task pipeline is
# failing (look for the subtask_foo in the traceback), and allows us to re-use
# these subtasks when testing failure scenarios.

def test_refuses_to_provision_synchronously(client):
    client.provision_alb_instance("4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_synchronously_by_default(client):
    client.provision_alb_instance("4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_provision_without_domains(client):
    client.provision_cdn_instance("4321")

    assert "domains" in client.response.body
    assert client.response.status_code == 400


def test_refuses_to_provision_with_duplicate_domains(client, dns):
    CdnServiceInstanceFactory.create(domain_names=["foo.com", "bar.com"])
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    client.provision_cdn_instance("4321", params={"domains": "example.com, foo.com"})

    assert "already exists" in client.response.body, client.response.body
    assert client.response.status_code == 400, client.response.body


def test_duplicate_domain_check_ignores_deactivated(client, dns):
    CdnServiceInstanceFactory.create(
        domain_names="foo.com", deactivated_at=datetime.utcnow()
    )
    dns.add_cname("_acme-challenge.foo.com")

    client.provision_cdn_instance("4321", params={"domains": "foo.com"})

    assert client.response.status_code == 202, client.response.body


def test_refuses_to_provision_without_any_acme_challenge_CNAMEs(client):
    client.provision_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com " in desc
    assert "_acme-challenge.foo.com.domains.cloud.test" in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_provision_without_one_acme_challenge_CNAME(client, dns):
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")
    assert "CNAME" in desc
    assert "_acme-challenge.foo.com" not in desc
    assert "_acme-challenge.bar.com " in desc
    assert "_acme-challenge.bar.com.domains.cloud.test" in desc
    assert client.response.status_code == 400


def test_refuses_to_provision_with_incorrect_acme_challenge_CNAME(client, dns):
    dns.add_cname("_acme-challenge.bar.com")
    dns.add_cname("_acme-challenge.foo.com", target="INCORRECT")
    client.provision_cdn_instance("4321", params={"domains": "bar.com,foo.com"})

    desc = client.response.json.get("description")

    assert "is set incorrectly" in desc

    assert " _acme-challenge.foo.com " in desc
    assert " _acme-challenge.foo.com.domains.cloud.test" in desc
    assert " INCORRECT" in desc

    assert " _acme-challenge.bar.com" not in desc
    assert client.response.status_code == 400
