import pytest
from sqlalchemy import insert

from broker.tasks.route53 import (
    create_new_health_checks,
    delete_unused_health_checks,
    delete_health_checks,
    remove_old_DNS_records,
)
from broker.models import (
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
    Operation,
)

from tests.lib import factories


@pytest.fixture
def service_instance(
    clean_db,
    operation_id,
    service_instance_id,
    cloudfront_distribution_arn,
    new_cert_id,
    current_cert_id,
):
    service_instance = factories.CDNDedicatedWAFServiceInstanceFactory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_distribution_arn=cloudfront_distribution_arn,
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
        forwarded_headers=["HOST"],
        route53_health_checks=None,
    )
    new_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=new_cert_id,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        id=current_cert_id,
    )
    service_instance.current_certificate = current_cert
    service_instance.new_certificate = new_cert
    clean_db.session.add(service_instance)
    clean_db.session.add(current_cert)
    clean_db.session.add(new_cert)
    clean_db.session.commit()
    clean_db.session.expunge_all()
    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )
    return service_instance


@pytest.fixture
def service_instance_with_challenges(service_instance, current_cert_id):
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        certificate_id=current_cert_id,
        answered=True,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        certificate_id=current_cert_id,
        answered=True,
    )
    return service_instance


def test_route53_create_all_new_health_checks(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    route53,
):
    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert not service_instance.route53_health_checks

    for idx, domain_name in enumerate(service_instance.domain_names):
        route53.expect_create_health_check(service_instance_id, domain_name, idx)

    create_new_health_checks.call_local(operation_id)

    route53.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.route53_health_checks == [
        {
            "domain_name": "example.com",
            "health_check_id": "example.com ID",
        },
        {
            "domain_name": "foo.com",
            "health_check_id": "foo.com ID",
        },
    ]
    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Creating new health checks"


def test_route53_create_new_health_checks_idempotent(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    route53,
):
    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert not service_instance.route53_health_checks

    for idx, domain_name in enumerate(service_instance.domain_names):
        route53.expect_create_health_check(service_instance_id, domain_name, idx)

    create_new_health_checks.call_local(operation_id)
    route53.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.route53_health_checks == [
        {
            "domain_name": "example.com",
            "health_check_id": "example.com ID",
        },
        {
            "domain_name": "foo.com",
            "health_check_id": "foo.com ID",
        },
    ]

    create_new_health_checks.call_local(operation_id)
    route53.assert_no_pending_responses()


def test_route53_create_new_health_checks_unmigrated_cdn_instance(
    clean_db,
    route53,
    unmigrated_cdn_service_instance_operation_id,
):
    operation = clean_db.session.get(
        Operation, unmigrated_cdn_service_instance_operation_id
    )
    service_instance = operation.service_instance

    assert service_instance.route53_health_checks == None

    for idx, domain_name in enumerate(service_instance.domain_names):
        route53.expect_create_health_check(service_instance.id, domain_name, idx)

    create_new_health_checks.call_local(unmigrated_cdn_service_instance_operation_id)

    route53.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(CDNServiceInstance, service_instance.id)
    assert service_instance.route53_health_checks == [
        {
            "domain_name": "example.com",
            "health_check_id": "example.com ID",
        },
    ]


def test_route53_create_new_health_checks(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    route53,
):
    # simulate a situation with:
    #   existing health checks for example.com, foo.com
    #   incoming change of domain names to ["foo.com", "bar.com"]
    service_instance.route53_health_checks = [
        {
            "domain_name": "example.com",
            "health_check_id": "example.com ID",
        },
        {
            "domain_name": "foo.com",
            "health_check_id": "foo.com ID",
        },
    ]
    service_instance.domain_names = ["foo.com", "bar.com"]
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    route53.expect_create_health_check(service_instance_id, "bar.com", 0)

    create_new_health_checks.call_local(operation_id)

    route53.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.route53_health_checks == [
        {
            "domain_name": "bar.com",
            "health_check_id": "bar.com ID",
        },
        {
            "domain_name": "example.com",
            "health_check_id": "example.com ID",
        },
        {
            "domain_name": "foo.com",
            "health_check_id": "foo.com ID",
        },
    ]
    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Creating new health checks"


def test_route53_deletes_unused_health_checks(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    route53,
):
    # simulate a situation with:
    #   existing health checks for example.com, foo.com
    #   incoming change of domain names to ["foo.com", "bar.com"]
    service_instance.route53_health_checks = [
        {
            "domain_name": "bar.com",
            "health_check_id": "bar.com ID",
        },
        {
            "domain_name": "example.com",
            "health_check_id": "example.com ID",
        },
        {
            "domain_name": "foo.com",
            "health_check_id": "foo.com ID",
        },
    ]
    service_instance.domain_names = ["foo.com", "bar.com"]
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    route53.expect_delete_health_check("example.com ID")

    delete_unused_health_checks.call_local(operation_id)

    route53.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.route53_health_checks == [
        {
            "domain_name": "bar.com",
            "health_check_id": "bar.com ID",
        },
        {
            "domain_name": "foo.com",
            "health_check_id": "foo.com ID",
        },
    ]
    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Deleting unused health checks"


def test_route53_deletes_health_checks(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    route53,
):
    # simulate a situation with:
    #   existing health checks for example.com, foo.com
    service_instance.route53_health_checks = [
        {
            "domain_name": "example.com",
            "health_check_id": "example.com ID",
        },
        {
            "domain_name": "foo.com",
            "health_check_id": "foo.com ID",
        },
    ]
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    route53.expect_delete_health_check("example.com ID")
    route53.expect_delete_health_check("foo.com ID")

    delete_health_checks.call_local(operation_id)

    route53.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.route53_health_checks == []
    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Deleting health checks"


def test_route53_deletes_health_checks_empty(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    route53,
):
    service_instance.route53_health_checks = []
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    delete_health_checks.call_local(operation_id)

    route53.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.route53_health_checks == []


def test_route53_deletes_health_checks_unmigrated_cdn_dedicated_waf_instance(
    clean_db,
    service_instance_id,
    unmigrated_cdn_dedicated_waf_service_instance_operation_id,
    route53,
):
    delete_health_checks.call_local(
        unmigrated_cdn_dedicated_waf_service_instance_operation_id,
    )

    route53.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.route53_health_checks == None


def test_route53_deletes_old_DNS_records(
    clean_db, route53, service_instance_with_challenges, operation_id
):
    # simulate a change in domain names
    service_instance_with_challenges.domain_names = ["bar.com", "cow.com"]

    clean_db.session.add(service_instance_with_challenges)
    clean_db.session.commit()

    route53.expect_remove_TXT(
        "_acme-challenge.example.com.domains.cloud.test", "example txt"
    )
    route53.expect_remove_ALIAS(
        "example.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    route53.expect_remove_TXT("_acme-challenge.foo.com.domains.cloud.test", "foo txt")
    route53.expect_remove_ALIAS("foo.com.domains.cloud.test", "fake1234.cloudfront.net")

    remove_old_DNS_records.call_local(operation_id)

    route53.assert_no_pending_responses()


def test_route53_deletes_old_DNS_records_ignores_errors(
    clean_db, route53, service_instance_with_challenges, operation_id
):
    # simulate a change in domain names
    service_instance_with_challenges.domain_names = ["bar.com", "cow.com"]

    clean_db.session.add(service_instance_with_challenges)
    clean_db.session.commit()

    # error should be ignored
    route53.expect_remove_missing_TXT(
        "_acme-challenge.example.com.domains.cloud.test", "example txt"
    )
    route53.expect_remove_ALIAS(
        "example.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    route53.expect_remove_TXT("_acme-challenge.foo.com.domains.cloud.test", "foo txt")
    # error should be ignored
    route53.expect_remove_missing_ALIAS(
        "foo.com.domains.cloud.test", "fake1234.cloudfront.net"
    )

    remove_old_DNS_records.call_local(operation_id)

    route53.assert_no_pending_responses()
