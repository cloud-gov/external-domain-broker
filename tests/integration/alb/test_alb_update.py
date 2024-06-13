from datetime import date, datetime

import pytest  # noqa F401

from broker.extensions import db
from broker.models import ALBServiceInstance

from tests.lib import factories
from tests.lib.client import check_last_operation_description

from tests.lib.update import (
    subtest_update_creates_update_operation,
    subtest_update_creates_private_key_and_csr,
    subtest_gets_new_challenges,
    subtest_update_updates_TXT_records,
    subtest_update_answers_challenges,
    subtest_waits_for_dns_changes,
    subtest_update_retrieves_new_cert,
    subtest_update_uploads_new_cert,
    subtest_update_marks_update_complete,
    subtest_update_removes_certificate_from_iam,
)


def subtest_update_happy_path(
    client, dns, tasks, route53, iam_govcloud, simple_regex, alb
):
    operation_id = subtest_update_creates_update_operation(client, dns)
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_update_creates_private_key_and_csr(tasks)
    subtest_gets_new_challenges(tasks)
    subtest_update_updates_TXT_records(tasks, route53)
    subtest_waits_for_dns_changes(tasks, route53)
    subtest_update_answers_challenges(tasks, dns)
    subtest_update_retrieves_new_cert(tasks)
    subtest_update_uploads_new_cert(tasks, iam_govcloud, simple_regex)
    subtest_update_selects_alb(tasks, alb)
    subtest_update_adds_certificate_to_alb(tasks, alb)
    subtest_update_provisions_ALIAS_records(tasks, route53, alb)
    subtest_waits_for_dns_changes(tasks, route53)
    subtest_update_removes_certificate_from_alb(tasks, alb)
    subtest_update_removes_certificate_from_iam(tasks, iam_govcloud)
    subtest_update_marks_update_complete(tasks)


def subtest_update_selects_alb(tasks, alb):
    db.session.expunge_all()
    alb.expect_get_certificates_for_listener("listener-arn-0", 1)
    alb.expect_get_certificates_for_listener("listener-arn-1", 5)
    alb.expect_get_listeners("listener-arn-0")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    service_instance = db.session.get(ALBServiceInstance, "4321")
    assert service_instance.alb_arn.startswith("alb-listener-arn-0")


def subtest_update_adds_certificate_to_alb(tasks, alb):
    db.session.expunge_all()
    service_instance = db.session.get(ALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    id_ = certificate.id
    alb.expect_add_certificate_to_listener(
        "listener-arn-0", certificate.iam_server_certificate_arn
    )
    alb.expect_describe_alb("alb-listener-arn-0", "alb.cloud.test")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(ALBServiceInstance, "4321")

    assert service_instance.new_certificate is None
    assert service_instance.current_certificate is not None
    assert service_instance.current_certificate.id == id_


def subtest_update_provisions_ALIAS_records(tasks, route53, alb):
    db.session.expunge_all()
    service_instance = db.session.get(ALBServiceInstance, "4321")
    example_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "bar.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_update_marks_update_complete(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()
    service_instance = db.session.get(ALBServiceInstance, "4321")
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state


def subtest_update_removes_certificate_from_alb(tasks, alb):
    alb.expect_remove_certificate_from_listener(
        "listener-arn-0",
        f"arn:aws:iam::000000000000:server-certificate/alb/external-domains-test/4321-{date.today().isoformat()}-1",
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    alb.assert_no_pending_responses()


def subtest_update_noop(client):
    client.update_alb_instance("4321", params={"domains": "bar.com, Foo.com"})
    assert client.response.status_code == 200
