import pytest

from tests.lib import factories
from tests.lib.client import check_last_operation_description
from tests.integration.alb.test_alb_provisioning import (
    subtest_provision_adds_certificate_to_alb,
    subtest_provision_answers_challenges,
    subtest_provision_creates_LE_user,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_marks_operation_as_succeeded,
    subtest_provision_provisions_ALIAS_records,
    subtest_provision_retrieves_certificate,
    subtest_provision_selects_alb,
    subtest_provision_updates_TXT_records,
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_waits_for_route53_changes,
)
from tests.integration.alb.test_alb_update import (
    subtest_update_creates_private_key_and_csr,
)
from tests.integration.alb.test_alb_renewals import (
    subtest_renewal_removes_certificate_from_iam,
    subtest_renewal_removes_certificate_from_alb,
)

from broker.models import ALBServiceInstance


@pytest.fixture
def migration_instance(clean_db):
    service_instance = factories.MigrationServiceInstanceFactory.create(
        id="4321", domain_names=["example.com", "foo.com"]
    )
    return service_instance


@pytest.fixture
def full_update_example():
    # this one is used for the full pipeline test.
    # it's kinda finicky because we are reusing other tests that assume some inputs
    params = {}
    params["iam_server_certificate_id"] = "certificate_id"
    params["iam_server_certificate_arn"] = "certificate_arn"
    params["iam_server_certificate_name"] = "certificate_name"
    params["domain_internal"] = "alb.cloud.test"
    params["alb_arn"] = "arn:aws:alb"
    params["alb_listener_arn"] = "listener-arn-0"
    params["hosted_zone_id"] = "ALBHOSTEDZONEID"
    return params


@pytest.mark.parametrize(
    "missing_param",
    [
        "iam_server_certificate_name",
        "iam_server_certificate_id",
        "iam_server_certificate_arn",
        "alb_arn",
        "alb_listener_arn",
        "hosted_zone_id",
        "domain_internal",
    ],
)
def test_migration_update_fails_without_required_params(
    client, migration_instance, missing_param, full_update_example
):
    full_update_example.pop(missing_param)
    client.update_instance_to_alb("4321", params=full_update_example)
    assert client.response.status_code >= 400
    assert "missing" in client.response.json.get("description").lower()
    assert missing_param in client.response.json.get("description")


def test_can_update_migration_instance_to_alb(
    client, migration_instance, full_update_example
):
    client.update_instance_to_alb("4321", params=full_update_example)
    assert client.response.status_code == 202, client.response.json


def test_migration_creates_certificate_record(
    client, migration_instance, full_update_example, clean_db
):
    client.update_instance_to_alb("4321", params=full_update_example)
    assert client.response.status_code == 202
    clean_db.session.expunge_all()
    instance = ALBServiceInstance.query.get("4321")
    assert instance.current_certificate is not None
    assert instance.current_certificate.iam_server_certificate_id == "certificate_id"
    assert instance.current_certificate.iam_server_certificate_arn == "certificate_arn"
    assert (
        instance.current_certificate.iam_server_certificate_name == "certificate_name"
    )
    assert instance.domain_internal == "alb.cloud.test"
    assert instance.route53_alias_hosted_zone == "ALBHOSTEDZONEID"
    assert instance.alb_listener_arn is not None
    assert instance.alb_arn is not None


def test_migration_pipeline(
    clean_db,
    client,
    tasks,
    migration_instance,
    route53,
    dns,
    iam_govcloud,
    simple_regex,
    full_update_example,
    alb,
):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.update_instance_to_alb("4321", params=full_update_example)
    subtest_provision_creates_LE_user(tasks)
    subtest_update_creates_private_key_and_csr(tasks)
    subtest_provision_initiates_LE_challenge(tasks)
    subtest_provision_provisions_ALIAS_records(tasks, route53, alb)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_updates_TXT_records(tasks, route53)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_answers_challenges(tasks, dns)
    subtest_provision_retrieves_certificate(tasks)
    subtest_provision_uploads_certificate_to_iam(tasks, iam_govcloud, simple_regex)
    subtest_provision_selects_alb(tasks, alb)
    subtest_provision_adds_certificate_to_alb(tasks, alb)
    subtest_provision_provisions_ALIAS_records(tasks, route53, alb)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_renewal_removes_certificate_from_alb(tasks, alb)
    subtest_renewal_removes_certificate_from_iam(tasks, iam_govcloud)
    subtest_provision_marks_operation_as_succeeded(tasks)
