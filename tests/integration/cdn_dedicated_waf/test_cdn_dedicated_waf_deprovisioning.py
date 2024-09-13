import pytest  # noqa F401
import uuid

from broker.extensions import db
from broker.models import CDNDedicatedWAFServiceInstance
from broker.tasks.cloudwatch import _get_alarm_name

from tests.lib import factories
from tests.lib.client import check_last_operation_description
from tests.lib.cdn.deprovision import (
    subtest_deprovision_creates_deprovision_operation,
    subtest_deprovision_removes_TXT_records_when_missing,
    subtest_deprovision_removes_ALIAS_records_when_missing,
    subtest_deprovision_removes_ALIAS_records,
    subtest_deprovision_disables_cloudfront_distribution,
    subtest_deprovision_waits_for_cloudfront_distribution_disabled,
    subtest_deprovision_removes_cloudfront_distribution,
    subtest_deprovision_disables_cloudfront_distribution_when_missing,
    subtest_deprovision_waits_for_cloudfront_distribution_disabled_when_missing,
    subtest_deprovision_removes_cloudfront_distribution_when_missing,
)
from tests.lib.deprovision import (
    subtest_deprovision_removes_TXT_records,
    subtest_deprovision_removes_certificate_from_iam,
    subtest_deprovision_marks_operation_as_succeeded,
    subtest_deprovision_removes_certificate_from_iam_when_missing,
)


@pytest.fixture
def protection_id():
    return str(uuid.uuid4())


@pytest.fixture
def service_instance(protection_id):
    service_instance = factories.CDNDedicatedWAFServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        shield_associated_health_check={
            "protection_id": protection_id,
            "health_check_id": "example.com ID",
            "domain_name": "example.com",
        },
        route53_health_checks=[
            {
                "domain_name": "example.com",
                "health_check_id": "example.com ID",
            },
            {
                "domain_name": "foo.com",
                "health_check_id": "foo.com ID",
            },
        ],
        cloudwatch_health_check_alarms=[
            {
                "health_check_id": "example.com ID",
                "alarm_name": _get_alarm_name("example.com ID"),
            },
            {
                "health_check_id": "foo.com ID",
                "alarm_name": _get_alarm_name("foo.com ID"),
            },
        ],
        dedicated_waf_web_acl_id="1234-dedicated-waf-id",
        dedicated_waf_web_acl_name="1234-dedicated-waf",
        dedicated_waf_web_acl_arn="1234-dedicated-waf-arn",
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
    shield,
    wafv2,
    cloudwatch_commercial,
):
    instance_model = CDNDedicatedWAFServiceInstance

    subtest_deprovision_creates_deprovision_operation(instance_model, client)
    subtest_deprovision_removes_ALIAS_records_when_missing(tasks, route53)
    subtest_deprovision_removes_TXT_records_when_missing(tasks, route53)
    subtest_deprovision_deletes_health_check_alarms_when_missing(
        instance_model, tasks, service_instance, cloudwatch_commercial
    )
    subtest_deprovision_disassociate_health_check_when_missing(
        instance_model, tasks, service_instance, shield
    )
    subtest_deprovision_deletes_health_checks_when_missing(
        instance_model, tasks, service_instance, route53
    )
    subtest_deprovision_disables_cloudfront_distribution_when_missing(
        instance_model, tasks, service_instance, cloudfront
    )
    subtest_deprovision_waits_for_cloudfront_distribution_disabled_when_missing(
        instance_model, tasks, service_instance, cloudfront
    )
    subtest_deprovision_removes_cloudfront_distribution_when_missing(
        instance_model, tasks, service_instance, cloudfront
    )
    subtest_deprovision_delete_web_acl_success_when_missing(
        instance_model, tasks, service_instance, wafv2
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
    shield,
    wafv2,
    cloudwatch_commercial,
):
    instance_model = CDNDedicatedWAFServiceInstance
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
    subtest_deprovision_deletes_health_check_alarms(
        instance_model, tasks, service_instance, cloudwatch_commercial
    )
    check_last_operation_description(
        client,
        "1234",
        operation_id,
        "Deleting Cloudwatch alarms for Route53 health checks",
    )
    subtest_deprovision_disassociate_health_check(
        instance_model, tasks, service_instance, shield
    )
    check_last_operation_description(
        client, "1234", operation_id, "Disassociating health check with Shield"
    )
    subtest_deprovision_deletes_health_checks(
        instance_model, tasks, service_instance, route53
    )
    check_last_operation_description(
        client, "1234", operation_id, "Deleting health checks"
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
    subtest_deprovision_deletes_web_acl(instance_model, tasks, service_instance, wafv2)
    check_last_operation_description(
        client, "1234", operation_id, "Deleting custom WAFv2 web ACL"
    )
    subtest_deprovision_removes_certificate_from_iam(
        instance_model, tasks, service_instance, iam_commercial
    )
    check_last_operation_description(
        client, "1234", operation_id, "Removing SSL certificate from AWS"
    )
    subtest_deprovision_marks_operation_as_succeeded(instance_model, tasks)
    check_last_operation_description(client, "1234", operation_id, "Complete!")


def subtest_deprovision_disassociate_health_check_when_missing(
    instance_model, tasks, service_instance, shield
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    shield.expect_disassociate_health_check_not_found(
        service_instance.shield_associated_health_check["protection_id"],
        "example.com ID",
    )
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")

    assert service_instance.shield_associated_health_check == None

    shield.assert_no_pending_responses()


def subtest_deprovision_deletes_health_checks_when_missing(
    instance_model, tasks, service_instance, route53
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    route53.expect_delete_health_check_not_found("example.com ID")
    route53.expect_delete_health_check_not_found("foo.com ID")
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert service_instance.route53_health_checks == []

    route53.assert_no_pending_responses()


def subtest_deprovision_delete_web_acl_success_when_missing(
    instance_model, tasks, service_instance, wafv2
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    wafv2.expect_get_web_acl_not_found(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert not service_instance.dedicated_waf_web_acl_id
    assert not service_instance.dedicated_waf_web_acl_arn
    assert not service_instance.dedicated_waf_web_acl_name
    wafv2.assert_no_pending_responses()


def subtest_deprovision_disassociate_health_check(
    instance_model, tasks, service_instance, shield
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")

    assert service_instance.shield_associated_health_check == {
        "protection_id": service_instance.shield_associated_health_check[
            "protection_id"
        ],
        "health_check_id": "example.com ID",
        "domain_name": "example.com",
    }

    shield.expect_disassociate_health_check(
        service_instance.shield_associated_health_check["protection_id"],
        "example.com ID",
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert service_instance.shield_associated_health_check == None

    shield.assert_no_pending_responses()


def subtest_deprovision_deletes_health_checks(
    instance_model, tasks, service_instance, route53
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert sorted(
        service_instance.route53_health_checks,
        key=lambda check: check["domain_name"],
    ) == [
        {
            "domain_name": "example.com",
            "health_check_id": "example.com ID",
        },
        {"domain_name": "foo.com", "health_check_id": "foo.com ID"},
    ]

    route53.expect_delete_health_check(
        "example.com ID",
    )
    route53.expect_delete_health_check(
        "foo.com ID",
    )
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert service_instance.route53_health_checks == []

    route53.assert_no_pending_responses()


def subtest_deprovision_deletes_web_acl(instance_model, tasks, service_instance, wafv2):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert service_instance.dedicated_waf_web_acl_arn == "1234-dedicated-waf-arn"
    assert service_instance.dedicated_waf_web_acl_id == "1234-dedicated-waf-id"
    assert service_instance.dedicated_waf_web_acl_name == "1234-dedicated-waf"

    wafv2.expect_get_web_acl(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )
    wafv2.expect_delete_web_acl(
        service_instance.dedicated_waf_web_acl_id,
        service_instance.dedicated_waf_web_acl_name,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert not service_instance.dedicated_waf_web_acl_arn
    assert not service_instance.dedicated_waf_web_acl_id
    assert not service_instance.dedicated_waf_web_acl_name

    wafv2.assert_no_pending_responses()


def subtest_deprovision_deletes_health_check_alarms(
    instance_model, tasks, service_instance, cloudwatch_commercial
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")

    assert service_instance.cloudwatch_health_check_alarms == [
        {
            "health_check_id": "example.com ID",
            "alarm_name": _get_alarm_name("example.com ID"),
        },
        {
            "health_check_id": "foo.com ID",
            "alarm_name": _get_alarm_name("foo.com ID"),
        },
    ]

    expect_delete_alarm_names = [
        _get_alarm_name("example.com ID"),
        _get_alarm_name("foo.com ID"),
    ]
    cloudwatch_commercial.expect_delete_alarms(expect_delete_alarm_names)

    tasks.run_queued_tasks_and_enqueue_dependents()

    cloudwatch_commercial.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert service_instance.cloudwatch_health_check_alarms == []


def subtest_deprovision_deletes_health_check_alarms_when_missing(
    instance_model, tasks, service_instance, cloudwatch_commercial
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    cloudwatch_commercial.expect_delete_alarms_not_found(
        [
            _get_alarm_name("example.com ID"),
            _get_alarm_name("foo.com ID"),
        ]
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    cloudwatch_commercial.assert_no_pending_responses()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "1234")
    assert service_instance.cloudwatch_health_check_alarms == []
