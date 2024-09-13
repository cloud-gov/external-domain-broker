from broker.extensions import db
from broker.models import Operation


def subtest_deprovision_creates_deprovision_operation(
    client, service_instance, instance_model
):
    service_instance = db.session.get(instance_model, "1234")
    client.deprovision_alb_instance(service_instance.id, accepts_incomplete="true")

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == Operation.States.IN_PROGRESS.value
    assert operation.action == Operation.Actions.DEPROVISION.value
    assert operation.service_instance_id == service_instance.id

    return operation_id


def subtest_deprovision_removes_ALIAS_records(tasks, route53):
    route53.expect_remove_ALIAS(
        "example.com.domains.cloud.test", "fake1234.cloud.test", "ALBHOSTEDZONEID"
    )
    route53.expect_remove_ALIAS(
        "foo.com.domains.cloud.test", "fake1234.cloud.test", "ALBHOSTEDZONEID"
    )

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


def subtest_deprovision_removes_cert_from_alb(
    tasks, service_instance, alb, instance_model
):
    service_instance = db.session.get(instance_model, "1234")
    alb.expect_remove_certificate_from_listener(
        service_instance.alb_listener_arn,
        service_instance.current_certificate.iam_server_certificate_arn,
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()


def subtest_deprovision_removes_certificate_from_iam(
    tasks, service_instance, iam_govcloud, instance_model
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


def subtest_deprovision_marks_operation_as_succeeded(tasks, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert not service_instance.deactivated_at

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert service_instance.deactivated_at

    operation = service_instance.operations.first()
    assert operation.state == "succeeded"
