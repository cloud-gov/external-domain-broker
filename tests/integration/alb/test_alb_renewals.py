from datetime import datetime, timedelta, date

import pytest

from broker.extensions import db
from broker.models import Operation, ALBServiceInstance
from broker.tasks.cron import scan_for_expiring_certs
from broker.tasks.huey import huey
from broker.tasks.letsencrypt import create_user, generate_private_key

from tests.integration.alb.test_alb_provisioning import (
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_answers_challenges,
    subtest_provision_retrieves_certificate,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_creates_private_key_and_csr,
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_selects_alb,
    subtest_provision_adds_certificate_to_alb,
    subtest_provision_provisions_ALIAS_records,
    subtest_provision_marks_operation_as_succeeded,
)
from tests.lib.factories import (
    ALBServiceInstanceFactory,
    OperationFactory,
    CertificateFactory,
)
from tests.lib.fake_cloudfront import FakeCloudFront


@pytest.fixture
def alb_instance_needing_renewal(clean_db, tasks):
    """
    create a cdn service instance that needs renewal.
    This includes walking it through the first few ACME steps to create a user so we can reuse that user.
    """
    renew_service_instance = ALBServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloud.test",
        route53_alias_hosted_zone="ALBHOSTEDZONEID",
        alb_arn="alb-arn-0",
        alb_listener_arn="listener-arn-0",
    )
    current_cert = CertificateFactory.create(
        id=1001,
        service_instance=renew_service_instance,
        expires_at=datetime.now() + timedelta(days=29),
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        iam_server_certificate_arn="certificate_arn",
        private_key_pem="SOMEPRIVATEKEY",
    )
    renew_service_instance.current_certificate = current_cert

    db.session.add(renew_service_instance)
    db.session.add(current_cert)
    db.session.commit()
    db.session.expunge_all()

    # create an operation, since that's what our task pipelines know to look for
    operation = OperationFactory.create(service_instance=renew_service_instance)
    db.session.refresh(operation)
    db.session.commit()

    huey.enqueue(create_user.s(operation.id))
    tasks.run_queued_tasks_and_enqueue_dependents()
    huey.enqueue(generate_private_key.s(operation.id))
    tasks.run_queued_tasks_and_enqueue_dependents()

    # delete the operation to simplify checks on operations later
    db.session.delete(operation)
    db.session.commit()
    return renew_service_instance


def test_scan_for_expiring_certs_alb_happy_path(
    clean_db,
    alb_instance_needing_renewal,
    tasks,
    route53,
    dns,
    iam_govcloud,
    simple_regex,
    cloudfront,
    alb,
):

    no_renew_service_instance = ALBServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.org", "foo.org"],
        domain_internal="fake1234.cloud.test",
        route53_alias_hosted_zone="ALBHOSTEDZONEID",
        alb_arn="alb-arn-0",
        alb_listener_arn="listener-arn-0",
    )
    no_renew_cert = CertificateFactory.create(
        id=1002,
        service_instance=no_renew_service_instance,
        expires_at=datetime.now() + timedelta(days=31),
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        iam_server_certificate_arn="certificate_arn",
    )
    no_renew_service_instance.current_certificate = no_renew_cert

    db.session.add(no_renew_service_instance)
    db.session.add(no_renew_cert)
    db.session.commit()
    db.session.expunge_all()
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    subtest_queues_tasks()
    subtest_provision_initiates_LE_challenge(tasks)
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


def subtest_queues_tasks():
    assert scan_for_expiring_certs.call_local() == ["4321"]
    service_instance = ALBServiceInstance.query.get("4321")

    assert len(list(service_instance.operations)) == 1
    operation = service_instance.operations[0]
    assert operation.action == Operation.Actions.RENEW.value
    assert len(huey.pending()) == 1


def test_does_queues_renewal_for_instance_with_canceled_operations(
    clean_db, alb_instance_needing_renewal
):
    # make a canceled operation
    operation = OperationFactory.create(
        service_instance=alb_instance_needing_renewal,
        state=Operation.States.IN_PROGRESS.value,
        canceled_at=datetime.now(),
    )
    db.session.add(operation)
    db.session.commit()
    instance = ALBServiceInstance.query.get("4321")
    assert not instance.has_active_operations()
    # this will queue an operation
    assert scan_for_expiring_certs.call_local() == ["4321"]
    instance = ALBServiceInstance.query.get("4321")
    assert instance.has_active_operations()
    assert scan_for_expiring_certs.call_local() == []


@pytest.mark.parametrize(
    "state", [Operation.States.FAILED.value, Operation.States.SUCCEEDED.value]
)
def test_queues_renewal_operations_not_in_progress(
    clean_db, state, alb_instance_needing_renewal
):
    operation = OperationFactory.create(
        service_instance=alb_instance_needing_renewal, state=state
    )
    db.session.add(operation)
    db.session.commit()
    instance = ALBServiceInstance.query.get("4321")
    assert not instance.has_active_operations()
    # this will queue an operation
    assert scan_for_expiring_certs.call_local() == ["4321"]
    instance = ALBServiceInstance.query.get("4321")
    assert instance.has_active_operations()
    assert scan_for_expiring_certs.call_local() == []


@pytest.mark.parametrize(
    "action",
    [
        Operation.Actions.DEPROVISION.value,
        Operation.Actions.PROVISION.value,
        Operation.Actions.RENEW.value,
    ],
)
def test_does_not_queue_for_in_progress_actions(
    clean_db, action, alb_instance_needing_renewal
):
    operation = OperationFactory.create(
        service_instance=alb_instance_needing_renewal,
        state=Operation.States.IN_PROGRESS.value,
        action=action,
    )
    db.session.add(operation)
    db.session.commit()
    instance = ALBServiceInstance.query.get("4321")
    assert instance.has_active_operations()
    assert scan_for_expiring_certs.call_local() == []


def subtest_renewal_removes_certificate_from_alb(tasks, alb):
    alb.expect_remove_certificate_from_listener("listener-arn-0", "certificate_arn")

    tasks.run_queued_tasks_and_enqueue_dependents()

    alb.assert_no_pending_responses()


def subtest_renewal_removes_certificate_from_iam(tasks, iam_govcloud):
    iam_govcloud.expects_delete_server_certificate("certificate_name")

    tasks.run_queued_tasks_and_enqueue_dependents()

    iam_govcloud.assert_no_pending_responses()
    instance = ALBServiceInstance.query.get("4321")
    assert len(instance.certificates) == 1
