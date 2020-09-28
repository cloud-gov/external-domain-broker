import json
from datetime import date, datetime

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import Challenge, Operation, CDNServiceInstance
from broker.tasks.cron import reschedule_operation
from broker.tasks.huey import huey
from broker.tasks.letsencrypt import create_user, generate_private_key

from tests.lib import factories
from tests.lib.client import check_last_operation_description
from tests.integration.cdn.test_cdn_provisioning import (
    subtest_provision_creates_LE_user,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_answers_challenges,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_marks_operation_as_succeeded,
)
from tests.integration.cdn.test_cdn_update import (
    subtest_update_creates_private_key_and_csr,
)
from tests.integration.cdn.test_cdn_renewals import (
    subtest_renew_retrieves_certificate,
    subtest_renewal_removes_certificate_from_iam,
    subtest_updates_certificate_in_cloudfront,
)


@pytest.fixture
def service_instance():
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone=None,
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
    )
    current_cert = factories.CertificateFactory.create(
        id=1001,
        service_instance=service_instance,
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_arn="certificate_arn",
        iam_server_certificate_name="certificate_name",
        # we're not copying these over
        leaf_pem=None,
        fullchain_pem=None,
        private_key_pem=None,
    )
    operation = factories.OperationFactory.create(
        id=1234,
        service_instance=service_instance,
        action=Operation.Actions.MIGRATE_TO_BROKER.value,
        state=Operation.States.IN_PROGRESS.value,
    )
    service_instance.current_certificate = current_cert
    db.session.add(service_instance)
    db.session.add(current_cert)
    db.session.add(operation)
    db.session.commit()
    db.session.expunge_all()
    return service_instance


def test_test_setup(clean_db, service_instance):
    # this test makes sure our fixtures don't do magic we don't want them too.
    # probably unnecessary, but it's fast and I already wrote it
    service_instance = CDNServiceInstance.query.get("4321")
    assert service_instance.current_certificate.challenges.all() == []
    assert service_instance.acme_user is None
    assert service_instance.has_active_operations()


def test_migration_pipeline(
    clean_db,
    tasks,
    service_instance,
    cloudfront,
    route53,
    dns,
    iam_commercial,
    simple_regex,
):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    reschedule_operation(1234)
    subtest_removes_s3_bucket(tasks, cloudfront)
    subtest_provision_creates_LE_user(tasks)
    subtest_update_creates_private_key_and_csr(tasks)
    subtest_provision_initiates_LE_challenge(tasks)
    subtest_provision_updates_TXT_records(tasks, route53)
    subtest_provision_waits_for_route53_changes(tasks, route53)
    subtest_provision_answers_challenges(tasks, dns)
    subtest_renew_retrieves_certificate(tasks)
    subtest_provision_uploads_certificate_to_iam(tasks, iam_commercial, simple_regex)
    subtest_updates_certificate_in_cloudfront(tasks, cloudfront)
    subtest_renewal_removes_certificate_from_iam(tasks, iam_commercial)
    subtest_provision_marks_operation_as_succeeded(tasks)


def subtest_removes_s3_bucket(tasks, cloudfront):
    db.session.expunge_all()
    service_instance = CDNServiceInstance.query.get("4321")
    cloudfront.expect_get_distribution_config(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        include_le_bucket=True,
    )
    cloudfront.expect_update_distribution(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=service_instance.current_certificate.iam_server_certificate_id,
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="FakeDistributionId",
        distribution_hostname="example.cloudfront.net",
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
