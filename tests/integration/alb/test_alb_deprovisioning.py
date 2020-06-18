import pytest  # noqa F401

from broker.extensions import db
from broker.models import Operation, ALBServiceInstance
from tests.lib import factories


@pytest.fixture
def service_instance():
    service_instance = factories.ALBServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com", "foo.com"],
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        iam_server_certificate_arn="certificate_arn",
        domain_internal="fake1234.cloud.test",
        alb_arn="alb-arn-0",
        alb_listener_arn="listener-arn-0",
        private_key_pem="SOMEPRIVATEKEY",
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
    client.deprovision_cdn_instance(service_instance.id, accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_deprovision_synchronously_by_default(client, service_instance):
    client.deprovision_cdn_instance(service_instance.id, accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_deprovision_happy_path(
    client, service_instance, dns, tasks, route53, iam_govcloud, simple_regex, alb
):
    subtest_deprovision_creates_deprovision_operation(client, service_instance)
    subtest_deprovision_removes_ALIAS_records(tasks, route53)
    subtest_deprovision_removes_TXT_records(tasks, route53)
    subtest_deprovision_removes_cert_from_alb(tasks, service_instance, alb)
    subtest_deprovision_removes_certificate_from_iam(
        tasks, service_instance, iam_govcloud
    )
    subtest_deprovision_marks_operation_as_succeeded(tasks)


def subtest_deprovision_creates_deprovision_operation(client, service_instance):
    client.deprovision_alb_instance(service_instance.id, accepts_incomplete="true")

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == Operation.States.IN_PROGRESS.value
    assert operation.action == Operation.Actions.DEPROVISION.value
    assert operation.service_instance_id == service_instance.id


def subtest_deprovision_removes_ALIAS_records(tasks, route53):
    route53.expect_remove_ALIAS("example.com.domains.cloud.test", "fake1234.cloud.test")
    route53.expect_remove_ALIAS("foo.com.domains.cloud.test", "fake1234.cloud.test")

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_removes_TXT_records(tasks, route53):
    route53.expect_remove_TXT(
        "_acme-challenge.example.com.domains.cloud.test", "example txt"
    )
    route53.expect_remove_TXT("_acme-challenge.foo.com.domains.cloud.test", "foo txt")

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_removes_cert_from_alb(tasks, service_instance, alb):
    alb.expect_remove_certificate_from_listener(
        service_instance.alb_listener_arn, service_instance.iam_server_certificate_arn
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()


def subtest_deprovision_removes_certificate_from_iam(
    tasks, service_instance, iam_govcloud
):
    iam_govcloud.expects_delete_server_certificate(
        service_instance.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam_govcloud.assert_no_pending_responses()


def subtest_deprovision_removes_certificate_from_iam_when_missing(
    tasks, service_instance, iam_govcloud
):
    iam_govcloud.expects_delete_server_certificate_returning_no_such_entity(
        name=service_instance.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam_govcloud.assert_no_pending_responses()


def subtest_deprovision_marks_operation_as_succeeded(tasks):
    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("1234")
    assert not service_instance.deactivated_at

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = ALBServiceInstance.query.get("1234")
    assert service_instance.deactivated_at
    assert not service_instance.private_key_pem

    operation = service_instance.operations.first()
    assert operation.state == "succeeded"
