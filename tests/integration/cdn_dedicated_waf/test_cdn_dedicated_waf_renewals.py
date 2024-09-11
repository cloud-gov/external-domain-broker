from datetime import datetime, timedelta, date

import pytest

from broker.extensions import db
from broker.models import Operation, CDNDedicatedWAFServiceInstance
from broker.tasks.cron import scan_for_expiring_certs
from broker.tasks.huey import huey
from broker.tasks.letsencrypt import create_user, generate_private_key

from tests.lib.provision import (
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_answers_challenges,
    subtest_provision_marks_operation_as_succeeded,
)
from tests.lib.cdn.provision import (
    subtest_provision_uploads_certificate_to_iam,
)
from tests.lib.cdn.update import (
    subtest_update_creates_private_key_and_csr,
)
from tests.lib.factories import (
    CDNDedicatedWAFServiceInstanceFactory,
    CertificateFactory,
    OperationFactory,
)
from tests.lib.fake_cloudfront import FakeCloudFront


@pytest.fixture
def cdn_instance_needing_renewal(clean_db, tasks):
    """
    create a cdn service instance that needs renewal.
    This includes walking it through the first few ACME steps to create a user so we can reuse that user.
    """
    renew_service_instance = CDNDedicatedWAFServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
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

    no_renew_service_instance = CDNDedicatedWAFServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.org", "foo.org"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
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

    instance_model = CDNDedicatedWAFServiceInstance

    subtest_queues_tasks()
    subtest_update_creates_private_key_and_csr(tasks, instance_model)
    subtest_provision_initiates_LE_challenge(tasks, instance_model)
    subtest_provision_updates_TXT_records(tasks, route53, instance_model)
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    subtest_provision_answers_challenges(tasks, dns, instance_model)
    subtest_renew_retrieves_certificate(tasks)
    subtest_provision_uploads_certificate_to_iam(
        tasks, iam_commercial, simple_regex, instance_model
    )
    subtest_updates_certificate_in_cloudfront(tasks, cloudfront)
    subtest_renewal_removes_certificate_from_iam(tasks, iam_commercial)
    subtest_provision_marks_operation_as_succeeded(tasks, instance_model)


def subtest_queues_tasks():
    assert scan_for_expiring_certs.call_local() == ["4321"]
    service_instance = db.session.get(CDNDedicatedWAFServiceInstance, "4321")

    assert len(list(service_instance.operations)) == 1
    operation = service_instance.operations[0]
    assert operation.action == Operation.Actions.RENEW.value
    assert len(huey.pending()) == 1


def subtest_updates_certificate_in_cloudfront(tasks, cloudfront: FakeCloudFront):
    cloudfront.expect_get_distribution_config(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id="certificate_id",
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        bucket_prefix="4321/",
    )
    cloudfront.expect_update_distribution(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id="FAKE_CERT_ID_XXXXXXXX",
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
        bucket_prefix="4321/",
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    cloudfront.assert_no_pending_responses()


def subtest_renew_retrieves_certificate(tasks):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(CDNDedicatedWAFServiceInstance, "4321")

    assert len(service_instance.certificates) == 2
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None


def subtest_renewal_removes_certificate_from_iam(tasks, iam_govcloud):
    iam_govcloud.expect_get_server_certificate("certificate_name")
    iam_govcloud.expects_delete_server_certificate("certificate_name")

    tasks.run_queued_tasks_and_enqueue_dependents()

    iam_govcloud.assert_no_pending_responses()
    instance = db.session.get(CDNDedicatedWAFServiceInstance, "4321")
    assert len(instance.certificates) == 1
