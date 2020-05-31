import pytest
from openbrokerapi.service_broker import OperationState

from broker.models import Operation
from broker.extensions import db
from tests.lib import factories


@pytest.fixture
def service_instance():
    service_instance = factories.ServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com", "foo.com"],
        cloudfront_distribution_url="fake1234.cloudfront.net",
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        service_instance=service_instance,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        service_instance=service_instance,
    )
    db.session.refresh(service_instance)
    return service_instance


def test_refuses_to_deprovision_synchronously(client, service_instance):
    client.deprovision_instance(service_instance.id, accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_deprovision_synchronously_by_default(client, service_instance):
    client.deprovision_instance(service_instance.id, accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def subtest_deprovision_creates_deprovision_operation(client, service_instance):
    client.deprovision_instance(service_instance.id, accepts_incomplete="true")

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == OperationState.IN_PROGRESS
    assert operation.action == Operation.Actions.DEPROVISION
    assert operation.service_instance_id == service_instance.id


def subtest_deprovision_removes_ALIAS_records(tasks, service_instance, route53):
    route53.expect_remove_ALIAS(
        "example.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    route53.expect_remove_ALIAS("foo.com.domains.cloud.test", "fake1234.cloudfront.net")

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_removes_TXT_records(tasks, service_instance, route53):
    route53.expect_remove_TXT(
        "_acme-challenge.example.com.domains.cloud.test", "example txt",
    )
    route53.expect_remove_TXT("_acme-challenge.foo.com.domains.cloud.test", "foo txt")

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def test_deprovision_happy_path(
    client, service_instance, dns, tasks, route53, iam, simple_regex, cloudfront
):
    subtest_deprovision_creates_deprovision_operation(client, service_instance)
    subtest_deprovision_removes_ALIAS_records(tasks, service_instance, route53)
    subtest_deprovision_removes_TXT_records(tasks, service_instance, route53)
    # subtest_deprovision_removes_cloudfront_distribution(tasks, service_instance, cloudfront)
    # subtest_deprovision_removes_certificate_from_iam(tasks, service_instance, iam, simple_regex)
    # subtest_deprovision_waits_for_route53_changes(tasks, service_instance, route53)
    # subtest_deprovision_removes_LE_certificate(tasks, service_instance)
    # subtest_deprovision_removes_LE_user(tasks, service_instance)
    # subtest_deprovision_marks_operation_as_succeeded(tasks, service_instance)

