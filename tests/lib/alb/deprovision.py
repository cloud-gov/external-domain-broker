from broker.extensions import db
from broker.models import ALBServiceInstance


def subtest_deprovision_removes_certificate_from_iam(
    tasks, service_instance, iam_govcloud
):
    service_instance = db.session.get(ALBServiceInstance, "1234")
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


def subtest_deprovision_removes_certificate_from_iam_when_missing(
    tasks, service_instance, iam_govcloud
):
    service_instance = db.session.get(ALBServiceInstance, "1234")
    iam_govcloud.expect_get_server_certificate_returning_no_such_entity(
        name=service_instance.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam_govcloud.assert_no_pending_responses()
