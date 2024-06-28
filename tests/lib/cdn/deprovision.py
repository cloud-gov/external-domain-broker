import pytest  # noqa F401

from broker.extensions import db
from broker.models import Operation


def subtest_deprovision_creates_deprovision_operation(instance_model, client):
    client.deprovision_instance(instance_model, "1234", accepts_incomplete="true")

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == Operation.States.IN_PROGRESS.value
    assert operation.action == Operation.Actions.DEPROVISION.value
    assert operation.service_instance_id == "1234"

    return operation_id


def subtest_deprovision_removes_TXT_records_when_missing(tasks, route53):
    route53.expect_remove_missing_TXT(
        "example.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    route53.expect_remove_missing_TXT(
        "foo.com.domains.cloud.test", "fake1234.cloudfront.net"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_removes_ALIAS_records_when_missing(tasks, route53):
    route53.expect_remove_missing_ALIAS(
        "_acme-challenge.example.com.domains.cloud.test", "example txt"
    )
    route53.expect_remove_missing_ALIAS(
        "_acme-challenge.foo.com.domains.cloud.test", "foo txt"
    )

    # one for marking provisioning tasks canceled, which is tested elsewhere
    tasks.run_queued_tasks_and_enqueue_dependents()
    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_removes_ALIAS_records(tasks, route53):
    route53.expect_remove_ALIAS(
        "example.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    route53.expect_remove_ALIAS("foo.com.domains.cloud.test", "fake1234.cloudfront.net")

    # one for marking provisioning tasks canceled, which is tested elsewhere
    tasks.run_queued_tasks_and_enqueue_dependents()
    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_removes_TXT_records(tasks, route53):
    route53.expect_remove_TXT(
        "_acme-challenge.example.com.domains.cloud.test", "example txt"
    )
    route53.expect_remove_TXT("_acme-challenge.foo.com.domains.cloud.test", "foo txt")

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_disables_cloudfront_distribution(
    instance_model, tasks, service_instance, cloudfront
):
    service_instance = db.session.get(instance_model, "1234")
    cloudfront.expect_get_distribution_config(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
    )
    cloudfront.expect_disable_distribution(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
        distribution_hostname=service_instance.domain_internal,
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    cloudfront.assert_no_pending_responses()


def subtest_deprovision_waits_for_cloudfront_distribution_disabled(
    instance_model, tasks, service_instance, cloudfront
):
    service_instance = db.session.get(instance_model, "1234")
    cloudfront.expect_get_distribution(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
        status="Deployed",
        enabled=True,
    )
    cloudfront.expect_get_distribution(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
        status="Deployed",
        enabled=False,
    )
    tasks.run_queued_tasks_and_enqueue_dependents()

    cloudfront.assert_no_pending_responses()


def subtest_deprovision_removes_cloudfront_distribution(
    instance_model, tasks, service_instance, cloudfront
):
    service_instance = db.session.get(instance_model, "1234")
    cloudfront.expect_get_distribution(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
        status="Deployed",
        enabled=False,
    )
    cloudfront.expect_delete_distribution(
        distribution_id=service_instance.cloudfront_distribution_id
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    cloudfront.assert_no_pending_responses()


def subtest_deprovision_disables_cloudfront_distribution_when_missing(
    instance_model, tasks, service_instance, cloudfront
):
    service_instance = db.session.get(instance_model, "1234")
    cloudfront.expect_get_distribution_config_returning_no_such_distribution(
        distribution_id=service_instance.cloudfront_distribution_id
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    cloudfront.assert_no_pending_responses()


def subtest_deprovision_waits_for_cloudfront_distribution_disabled_when_missing(
    instance_model, tasks, service_instance, cloudfront
):
    service_instance = db.session.get(instance_model, "1234")
    cloudfront.expect_get_distribution_returning_no_such_distribution(
        distribution_id=service_instance.cloudfront_distribution_id
    )
    tasks.run_queued_tasks_and_enqueue_dependents()

    cloudfront.assert_no_pending_responses()


def subtest_deprovision_removes_cloudfront_distribution_when_missing(
    instance_model, tasks, service_instance, cloudfront
):
    service_instance = db.session.get(instance_model, "1234")
    cloudfront.expect_get_distribution_returning_no_such_distribution(
        distribution_id=service_instance.cloudfront_distribution_id
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    cloudfront.assert_no_pending_responses()


def subtest_deprovision_removes_certificate_from_iam(
    instance_model, tasks, service_instance, iam_commercial
):
    service_instance = db.session.get(instance_model, "1234")
    iam_commercial.expects_delete_server_certificate(
        service_instance.new_certificate.iam_server_certificate_name
    )
    iam_commercial.expects_delete_server_certificate(
        service_instance.current_certificate.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam_commercial.assert_no_pending_responses()


def subtest_deprovision_removes_certificate_from_iam_when_missing(
    instance_model, tasks, service_instance, iam_commercial
):
    service_instance = db.session.get(instance_model, "1234")
    iam_commercial.expects_delete_server_certificate_returning_no_such_entity(
        name=service_instance.new_certificate.iam_server_certificate_name
    )
    iam_commercial.expects_delete_server_certificate_returning_no_such_entity(
        name=service_instance.current_certificate.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam_commercial.assert_no_pending_responses()


def subtest_deprovision_marks_operation_as_succeeded(instance_model, tasks):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert not service_instance.deactivated_at

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert service_instance.deactivated_at

    operation = service_instance.operations.first()
    assert operation.state == "succeeded"
