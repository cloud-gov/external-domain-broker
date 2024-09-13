from broker.extensions import db
from broker.models import Operation


def subtest_deprovision_creates_deprovision_operation(
    instance_model, client, service_instance
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


def subtest_deprovision_removes_cert_from_alb(
    instance_model, tasks, service_instance, alb
):
    service_instance = db.session.get(instance_model, "1234")
    alb.expect_remove_certificate_from_listener(
        service_instance.alb_listener_arn,
        service_instance.current_certificate.iam_server_certificate_arn,
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
