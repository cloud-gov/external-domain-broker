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
    subtest_provision_marks_operation_as_succeeded
)
from tests.lib.factories import ALBServiceInstanceFactory, OperationFactory
from tests.lib.fake_cloudfront import FakeCloudFront


@pytest.fixture
def cdn_instance_needing_renewal(clean_db, tasks):
    """
    create a cdn service instance that needs renewal.
    This includes walking it through the first few ACME steps to create a user so we can reuse that user.
    """
    renew_service_instance = ALBServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        iam_server_certificate_arn="certificate_arn",
        domain_internal="fake1234.cloud.test",
        route53_alias_hosted_zone="ALBHOSTEDZONEID",
        alb_arn="alb-arn-0",
        alb_listener_arn="listener-arn-0",
        private_key_pem="SOMEPRIVATEKEY",
        cert_expires_at=datetime.now() + timedelta(days=9),
    )

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
    cdn_instance_needing_renewal,
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
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        iam_server_certificate_arn="certificate_arn",
        domain_internal="fake1234.cloud.test",
        route53_alias_hosted_zone="ALBHOSTEDZONEID",
        alb_arn="alb-arn-0",
        alb_listener_arn="listener-arn-0",
        private_key_pem="SOMEPRIVATEKEY",
        cert_expires_at=datetime.now() + timedelta(days=11),
    )
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    db.session.refresh(no_renew_service_instance)
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
    subtest_provision_marks_operation_as_succeeded(tasks)



def subtest_queues_tasks():
    assert scan_for_expiring_certs.call_local() == ["4321"]
    service_instance = ALBServiceInstance.query.get("4321")

    assert len(list(service_instance.operations)) == 1
    operation = service_instance.operations[0]
    assert operation.action == Operation.Actions.RENEW.value
    assert len(huey.pending()) == 1

