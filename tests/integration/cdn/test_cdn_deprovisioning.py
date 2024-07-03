import pytest  # noqa F401

from broker.extensions import db
from broker.models import CDNServiceInstance
from tests.lib import factories
from tests.lib.client import check_last_operation_description
from tests.lib.cdn.deprovision import (
    subtest_deprovision_creates_deprovision_operation,
    subtest_deprovision_removes_TXT_records_when_missing,
    subtest_deprovision_removes_ALIAS_records_when_missing,
    subtest_deprovision_removes_ALIAS_records,
    subtest_deprovision_removes_TXT_records,
    subtest_deprovision_disables_cloudfront_distribution,
    subtest_deprovision_waits_for_cloudfront_distribution_disabled,
    subtest_deprovision_removes_cloudfront_distribution,
    subtest_deprovision_disables_cloudfront_distribution_when_missing,
    subtest_deprovision_waits_for_cloudfront_distribution_disabled_when_missing,
    subtest_deprovision_removes_cloudfront_distribution_when_missing,
    subtest_deprovision_removes_certificate_from_iam,
    subtest_deprovision_removes_certificate_from_iam_when_missing,
    subtest_deprovision_marks_operation_as_succeeded,
)


@pytest.fixture
def service_instance():
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
    )
    new_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="NEWSOMEPRIVATEKEY",
        leaf_pem="NEWSOMECERTPEM",
        fullchain_pem="NEWFULLCHAINOFSOMECERTPEM",
        iam_server_certificate_id="new_certificate_id",
        iam_server_certificate_arn="new_certificate_arn",
        iam_server_certificate_name="new_certificate_name",
        id=1002,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_arn="certificate_arn",
        iam_server_certificate_name="certificate_name",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1001,
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=1001,
        answered=True,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=1001,
        answered=True,
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=1002,
        answered=False,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=1002,
        answered=False,
    )
    service_instance.current_certificate = current_cert
    service_instance.new_certificate = new_cert
    db.session.add(service_instance)
    db.session.add(current_cert)
    db.session.add(new_cert)
    db.session.commit()
    db.session.expunge_all()
    return service_instance


def test_deprovision_continues_when_resources_dont_exist(
    client,
    service_instance,
    tasks,
    route53,
    iam_commercial,
    cloudfront,
):
    instance_model = CDNServiceInstance
    subtest_deprovision_creates_deprovision_operation(instance_model, client)
    subtest_deprovision_removes_ALIAS_records_when_missing(tasks, route53)
    subtest_deprovision_removes_TXT_records_when_missing(tasks, route53)

    subtest_deprovision_disables_cloudfront_distribution_when_missing(
        instance_model, tasks, service_instance, cloudfront
    )
    subtest_deprovision_waits_for_cloudfront_distribution_disabled_when_missing(
        instance_model, tasks, service_instance, cloudfront
    )
    subtest_deprovision_removes_cloudfront_distribution_when_missing(
        instance_model, tasks, service_instance, cloudfront
    )
    subtest_deprovision_removes_certificate_from_iam_when_missing(
        instance_model, tasks, service_instance, iam_commercial
    )


def test_deprovision_happy_path(
    client,
    service_instance,
    tasks,
    route53,
    iam_commercial,
    cloudfront,
):
    instance_model = CDNServiceInstance
    operation_id = subtest_deprovision_creates_deprovision_operation(
        instance_model, client
    )
    check_last_operation_description(client, "1234", operation_id, "Queuing tasks")
    subtest_deprovision_removes_ALIAS_records(tasks, route53)
    check_last_operation_description(
        client, "1234", operation_id, "Removing DNS ALIAS records"
    )
    subtest_deprovision_removes_TXT_records(tasks, route53)
    check_last_operation_description(
        client, "1234", operation_id, "Removing DNS TXT records"
    )
    subtest_deprovision_disables_cloudfront_distribution(
        instance_model, tasks, service_instance, cloudfront
    )
    check_last_operation_description(
        client, "1234", operation_id, "Disabling CloudFront distribution"
    )
    subtest_deprovision_waits_for_cloudfront_distribution_disabled(
        instance_model, tasks, service_instance, cloudfront
    )
    check_last_operation_description(
        client, "1234", operation_id, "Waiting for CloudFront distribution to disable"
    )
    subtest_deprovision_removes_cloudfront_distribution(
        instance_model, tasks, service_instance, cloudfront
    )
    check_last_operation_description(
        client, "1234", operation_id, "Deleting CloudFront distribution"
    )
    subtest_deprovision_removes_certificate_from_iam(
        instance_model, tasks, service_instance, iam_commercial
    )
    check_last_operation_description(
        client, "1234", operation_id, "Removing SSL certificate from AWS"
    )
    subtest_deprovision_marks_operation_as_succeeded(instance_model, tasks)
    check_last_operation_description(client, "1234", operation_id, "Complete!")
