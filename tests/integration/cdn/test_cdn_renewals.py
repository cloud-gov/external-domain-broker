from datetime import datetime, timedelta

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
)
from tests.lib.factories import CDNServiceInstanceFactory, OperationFactory

# TODO: move these to the test_*_provision to leverage already-created LE users
# alternately, add LE-user-creating fixture


@pytest.fixture
def cdn_instance_needing_renewal(tasks):
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
    operation = OperationFactory.create(service_instance=renew_service_instance)

    db.session.refresh(operation)
    db.session.commit()
    huey.enqueue(create_user.s(operation.id))
    tasks.run_queued_tasks_and_enqueue_dependents()
    huey.enqueue(generate_private_key.s(operation.id))
    tasks.run_queued_tasks_and_enqueue_dependents()
    return renew_service_instance


def test_scan_for_expiring_certs_cdn_happy_path(
    cdn_instance_needing_renewal, tasks, route53, dns
):

    no_renew_service_instance = CDNServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com", "foo.com"],
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

    db.session.refresh(no_renew_service_instance)
    subtest_queues_tasks()


def subtest_queues_tasks():
    assert scan_for_expiring_certs.call_local() == ["4321"]
    # assert len(huey.pending()) == 1
