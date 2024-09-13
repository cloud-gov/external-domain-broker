from broker.extensions import db
from broker.models import Operation


def subtest_deprovision_removes_certificate_from_iam(
    instance_model, tasks, service_instance, iam_govcloud
):
    service_instance = db.session.get(instance_model, "1234")
    iam_govcloud.expect_get_server_certificate(
        service_instance.new_certificate.iam_server_certificate_name
    )
    iam_govcloud.expects_delete_server_certificate(
        service_instance.new_certificate.iam_server_certificate_name
    )
    iam_govcloud.expect_get_server_certificate(
        service_instance.current_certificate.iam_server_certificate_name
    )
    iam_govcloud.expects_delete_server_certificate(
        service_instance.current_certificate.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam_govcloud.assert_no_pending_responses()


def subtest_deprovision_removes_TXT_records(tasks, route53):
    route53.expect_remove_TXT(
        "_acme-challenge.example.com.domains.cloud.test", "example txt"
    )
    route53.expect_remove_TXT("_acme-challenge.foo.com.domains.cloud.test", "foo txt")

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_removes_certificate_from_iam(
    instance_model, tasks, service_instance, iam
):
    service_instance = db.session.get(instance_model, "1234")
    iam.expect_get_server_certificate(
        service_instance.new_certificate.iam_server_certificate_name
    )
    iam.expects_delete_server_certificate(
        service_instance.new_certificate.iam_server_certificate_name
    )
    iam.expect_get_server_certificate(
        service_instance.current_certificate.iam_server_certificate_name
    )
    iam.expects_delete_server_certificate(
        service_instance.current_certificate.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam.assert_no_pending_responses()


def subtest_deprovision_removes_certificate_from_iam_when_missing(
    instance_model, tasks, service_instance, iam
):
    service_instance = db.session.get(instance_model, "1234")
    iam.expect_get_server_certificate_returning_no_such_entity(
        name=service_instance.new_certificate.iam_server_certificate_name
    )
    iam.expect_get_server_certificate_returning_no_such_entity(
        name=service_instance.current_certificate.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam.assert_no_pending_responses()


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
