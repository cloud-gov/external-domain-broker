from datetime import datetime, timedelta, date

import pytest

from broker.extensions import db
from broker.models import Operation, CDNServiceInstance
from broker.tasks.cron import scan_for_expiring_certs
from broker.tasks.huey import huey
from broker.tasks.letsencrypt import create_user, generate_private_key

from tests.integration.cdn.test_cdn_provisioning import (
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_answers_challenges,
    subtest_provision_retrieves_certificate,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_creates_private_key_and_csr,
    subtest_provision_uploads_certificate_to_iam,
)
from tests.lib.factories import CDNServiceInstanceFactory, OperationFactory
from tests.lib.fake_cloudfront import FakeCloudFront


@pytest.fixture
def cdn_instance_needing_renewal(clean_db, tasks):
    """
    create a cdn service instance that needs renewal.
    This includes walking it through the first few ACME steps to create a user so we can reuse that user.
    """
    renew_service_instance = CDNServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        private_key_pem="SOMEPRIVATEKEY",
        cert_expires_at=datetime.now() + timedelta(days=9),
    )

    # create an operation, since that's what our task pipelines know to look for
    operation = OperationFactory.create(service_instance=renew_service_instance)
    db.session.refresh(operation)
    db.session.commit()

    huey.enqueue(create_user.s(operation.id))
    tasks.run_queued_tasks_and_enqueue_dependents()
    # huey.enqueue(generate_private_key.s(operation.id))
    # tasks.run_queued_tasks_and_enqueue_dependents()

    # delete the operation to simplify checks on operations later
    db.session.delete(operation)
    db.session.commit()
    return renew_service_instance


def test_scan_for_expiring_certs_cdn_happy_path(
    clean_db,
    cdn_instance_needing_renewal,
    tasks,
    route53,
    dns,
    iam_commercial,
    simple_regex,
    cloudfront,
):

    no_renew_service_instance = CDNServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.org", "foo.org"],
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        private_key_pem="SOMEPRIVATEKEY",
        cert_expires_at=datetime.now() + timedelta(days=11),
    )
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")

    db.session.refresh(no_renew_service_instance)
    subtest_queues_tasks()
    subtest_provision_creates_private_key_and_csr(tasks)
    subtest_provision_initiates_LE_challenge(tasks)
    subtest_provision_updates_TXT_records(tasks, route53)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_answers_challenges(tasks, dns)
    subtest_provision_retrieves_certificate(tasks)
    subtest_provision_uploads_certificate_to_iam(tasks, iam_commercial, simple_regex)
    subtest_updates_certificate_in_cloudfront(tasks, cloudfront)


def subtest_queues_tasks():
    assert scan_for_expiring_certs.call_local() == ["4321"]
    service_instance = CDNServiceInstance.query.get("4321")

    # one for the renewal, one leftover from making the LE user
    assert len(list(service_instance.operations)) == 1
    operation = service_instance.operations[0]
    assert operation.action == Operation.Actions.RENEW.value
    assert len(huey.pending()) == 1


def subtest_updates_certificate_in_cloudfront(tasks, cloundfront: FakeCloudFront):
    cloundfront.expect_get_distribution_config(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id="certificate_id",
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
    )
    cloundfront.expect_update_distribution(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id="FAKE_CERT_ID_XXXXXXXX",
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    cloundfront.assert_no_pending_responses()
