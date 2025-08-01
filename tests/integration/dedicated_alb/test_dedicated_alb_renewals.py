from datetime import datetime, timedelta

from acme.errors import ValidationError
import pytest

from broker.extensions import db
from broker.models import (
    Operation,
    DedicatedALB,
    DedicatedALBListener,
    DedicatedALBServiceInstance,
)
from broker.tasks.cron import scan_for_expiring_certs
from broker.tasks.huey import huey
from broker.tasks.letsencrypt import create_user, generate_private_key

from tests.integration.dedicated_alb.test_dedicated_alb_provisioning import (
    subtest_provision_selects_dedicated_alb,
    subtest_provision_adds_certificate_to_alb,
)
from tests.lib.provision import (
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_answers_challenges,
    subtest_provision_marks_operation_as_succeeded,
)
from tests.lib.alb.provision import (
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_provisions_ALIAS_records,
    subtest_provision_retrieves_certificate,
)
from tests.lib.alb.update import (
    subtest_removes_previous_certificate_from_alb,
)
from tests.lib.update import (
    subtest_update_creates_private_key_and_csr,
)

from tests.lib.factories import (
    DedicatedALBServiceInstanceFactory,
    OperationFactory,
    CertificateFactory,
)

from tests.integration.dedicated_alb.provision import create_dedicated_alb_listeners


@pytest.fixture
def dedicated_alb_instance_needing_renewal(clean_db, tasks, organization_guid):
    """
    create a cdn service instance that needs renewal.
    This includes walking it through the first few ACME steps to create a user so we can reuse that user.
    """
    renew_service_instance = DedicatedALBServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloud.test",
        route53_alias_hosted_zone="ALBHOSTEDZONEID",
        alb_arn="alb-our-arn-0",
        alb_listener_arn="our-arn-0",
        org_id=organization_guid,
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
    dedicated_alb_instance_needing_renewal,
    tasks,
    route53,
    dns,
    iam_govcloud,
    simple_regex,
    alb,
    organization_guid,
    dedicated_alb_id,
    dedicated_alb_arn,
):

    no_renew_service_instance = DedicatedALBServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.org", "foo.org"],
        domain_internal="fake1234.cloud.test",
        route53_alias_hosted_zone="ALBHOSTEDZONEID",
        alb_arn="alb-our-arn-0",
        alb_listener_arn="our-arn-0",
        org_id="our-org",
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

    create_dedicated_alb_listeners(
        db, organization_guid, dedicated_alb_id, dedicated_alb_arn
    )

    instance_model = DedicatedALBServiceInstance
    subtest_queues_tasks()
    subtest_update_creates_private_key_and_csr(tasks, instance_model)
    subtest_provision_initiates_LE_challenge(tasks, instance_model)
    subtest_provision_updates_TXT_records(tasks, route53, instance_model)
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    subtest_provision_answers_challenges(tasks, dns, instance_model)
    subtest_provision_retrieves_certificate(tasks, instance_model)
    subtest_provision_uploads_certificate_to_iam(
        tasks, iam_govcloud, simple_regex, instance_model
    )
    subtest_provision_selects_dedicated_alb(tasks, alb, dedicated_alb_arn)
    subtest_provision_adds_certificate_to_alb(tasks, alb, dedicated_alb_arn)
    subtest_provision_provisions_ALIAS_records(tasks, route53, instance_model)
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    subtest_removes_previous_certificate_from_alb(
        tasks, alb, "our-arn-0", "certificate_arn"
    )
    subtest_renewal_removes_certificate_from_iam(tasks, iam_govcloud)
    subtest_provision_marks_operation_as_succeeded(tasks, instance_model)


def subtest_queues_tasks():
    assert scan_for_expiring_certs.call_local() == ["4321"]
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")

    assert len(list(service_instance.operations)) == 1
    operation = service_instance.operations[0]
    assert operation.action == Operation.Actions.RENEW.value
    assert len(huey.pending()) == 1


def test_does_queues_renewal_for_instance_with_canceled_operations(
    clean_db, dedicated_alb_instance_needing_renewal
):
    # make a canceled operation
    operation = OperationFactory.create(
        service_instance=dedicated_alb_instance_needing_renewal,
        state=Operation.States.IN_PROGRESS.value,
        canceled_at=datetime.now(),
    )
    db.session.add(operation)
    db.session.commit()
    instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert not instance.has_active_operations()
    # this will queue an operation
    assert scan_for_expiring_certs.call_local() == ["4321"]
    instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert instance.has_active_operations()
    assert scan_for_expiring_certs.call_local() == []


@pytest.mark.parametrize(
    "state", [Operation.States.FAILED.value, Operation.States.SUCCEEDED.value]
)
def test_queues_renewal_operations_not_in_progress(
    clean_db, state, dedicated_alb_instance_needing_renewal
):
    operation = OperationFactory.create(
        service_instance=dedicated_alb_instance_needing_renewal, state=state
    )
    db.session.add(operation)
    db.session.commit()
    instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert not instance.has_active_operations()
    # this will queue an operation
    assert scan_for_expiring_certs.call_local() == ["4321"]
    instance = db.session.get(DedicatedALBServiceInstance, "4321")
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
    clean_db, action, dedicated_alb_instance_needing_renewal
):
    operation = OperationFactory.create(
        service_instance=dedicated_alb_instance_needing_renewal,
        state=Operation.States.IN_PROGRESS.value,
        action=action,
    )
    db.session.add(operation)
    db.session.commit()
    instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert instance.has_active_operations()
    assert scan_for_expiring_certs.call_local() == []


def subtest_renewal_removes_certificate_from_iam(tasks, iam_govcloud):
    iam_govcloud.expect_get_server_certificate("certificate_name")
    iam_govcloud.expects_delete_server_certificate("certificate_name")

    tasks.run_queued_tasks_and_enqueue_dependents()

    iam_govcloud.assert_no_pending_responses()
    instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert len(instance.certificates) == 1


def test_cleanup_on_failed_challenges(
    clean_db,
    dedicated_alb_instance_needing_renewal,
    tasks,
    route53,
    dns,
):
    """
    When a renewal fails because the Lets Encrypt thinks we didn't solve the challenges
    we need to clean up the challenges and service_instance.new_certificate so that next
    time we try to renew, we won't try to reuse them.
    """

    # note that we didn't do dns.add_cname(...)
    # that should be what causes the challenges to fail

    dns.add_txt(
        "_acme-challenge.example.com",
        "bad",
    )

    dns.add_txt(
        "_acme-challenge.foo.com",
        "bad",
    )

    # borrow subtests to get us to the right state
    subtest_queues_tasks()
    instance_model = DedicatedALBServiceInstance
    subtest_update_creates_private_key_and_csr(tasks, instance_model)
    subtest_provision_initiates_LE_challenge(tasks, instance_model)
    subtest_provision_updates_TXT_records(tasks, route53, instance_model)
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    subtest_provision_answers_challenges(tasks, dns, instance_model)

    # now do the stuff
    with pytest.raises(ValidationError):
        tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    assert certificate is None
