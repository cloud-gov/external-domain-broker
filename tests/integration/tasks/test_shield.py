import pytest

from broker.tasks.shield import (
    associate_health_check,
    disassociate_health_check,
    update_associated_health_check,
)
from broker.models import CDNDedicatedWAFServiceInstance, Operation

from tests.lib import factories


@pytest.fixture
def service_instance(
    clean_db, operation_id, service_instance_id, cloudfront_distribution_arn
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
        route53_health_checks=[
            {"domain_name": "example.com", "health_check_id": "example.com ID"},
            {"domain_name": "foo.com", "health_check_id": "foo.com ID"},
        ],
    )
    new_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1002,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        id=1001,
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
def protection(protection_id, cloudfront_distribution_arn):
    return {
        "Id": protection_id,
        "ResourceArn": cloudfront_distribution_arn,
    }


def test_shield_associate_health_check(
    clean_db,
    protection_id,
    protection,
    service_instance_id,
    service_instance,
    operation_id,
    shield,
):
    shield.expect_list_protections([protection])
    shield.expect_associate_health_check(protection_id, "example.com ID")

    associate_health_check.call_local(operation_id)

    shield.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.shield_associated_health_check == {
        "domain_name": "example.com",
        "health_check_id": "example.com ID",
        "protection_id": protection_id,
    }
    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Associating health check with Shield"


def test_shield_associate_health_check_unmigrated_cdn_instance(
    clean_db,
    protection_id,
    protection,
    service_instance_id,
    shield,
    unmigrated_cdn_service_instance_operation_id,
):
    operation = clean_db.session.get(
        Operation, unmigrated_cdn_service_instance_operation_id
    )
    service_instance = operation.service_instance

    service_instance.route53_health_checks = [
        {"domain_name": "example.com", "health_check_id": "example.com ID"},
        {"domain_name": "foo.com", "health_check_id": "foo.com ID"},
    ]
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    shield.expect_list_protections([protection])
    shield.expect_associate_health_check(protection_id, "example.com ID")

    associate_health_check.call_local(unmigrated_cdn_service_instance_operation_id)

    shield.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.shield_associated_health_check == {
        "domain_name": "example.com",
        "health_check_id": "example.com ID",
        "protection_id": protection_id,
    }


def test_shield_update_no_existing_associated_health_check(
    clean_db,
    protection_id,
    protection,
    service_instance_id,
    service_instance,
    operation_id,
    shield,
):
    service_instance.shield_associated_health_check = {}

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    shield.expect_list_protections([protection])
    shield.expect_associate_health_check(protection_id, "example.com ID")

    update_associated_health_check.call_local(operation_id)

    # There should be no calls to associate or disassociate a health check with Shield
    shield.assert_no_pending_responses()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.shield_associated_health_check == {
        "domain_name": "example.com",
        "health_check_id": "example.com ID",
        "protection_id": protection_id,
    }
    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Updating associated health check with Shield"


def test_shield_update_no_change_associated_health_check(
    clean_db, protection_id, service_instance_id, service_instance, operation_id, shield
):
    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )

    # simulate a change in domain names to ["example.com", "foo.com"]
    service_instance.domain_names = ["example.com", "bar.com"]
    service_instance.route53_health_checks = [
        {"domain_name": "example.com", "health_check_id": "example.com ID"},
        {"domain_name": "bar.com", "health_check_id": "bar.com ID"},
    ]
    service_instance.shield_associated_health_check = {
        "domain_name": "example.com",
        "health_check_id": "example.com ID",
        "protection_id": protection_id,
    }
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    update_associated_health_check.call_local(operation_id)

    # There should be no calls to associate or disassociate a health check with Shield
    shield.assert_no_pending_responses()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.shield_associated_health_check == {
        "domain_name": "example.com",
        "health_check_id": "example.com ID",
        "protection_id": protection_id,
    }
    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Updating associated health check with Shield"


def test_shield_update_change_associated_health_check(
    clean_db,
    protection_id,
    protection,
    service_instance_id,
    service_instance,
    operation_id,
    shield,
):
    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )

    # simulate a change in domain names
    # example.com no longer in the domain names - expect associated health check to change
    service_instance.domain_names = ["bar.com", "cow.com"]
    service_instance.route53_health_checks = [
        {"domain_name": "bar.com", "health_check_id": "bar.com ID"},
        {"domain_name": "cow.com", "health_check_id": "cow.com ID"},
    ]
    service_instance.shield_associated_health_check = {
        "domain_name": "example.com",
        "health_check_id": "example.com ID",
        "protection_id": protection_id,
    }

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    shield.expect_disassociate_health_check(protection_id, "example.com ID")
    shield.expect_list_protections([protection])
    shield.expect_associate_health_check(protection_id, "bar.com ID")

    update_associated_health_check.call_local(operation_id)

    shield.assert_no_pending_responses()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.shield_associated_health_check == {
        "domain_name": "bar.com",
        "health_check_id": "bar.com ID",
        "protection_id": protection_id,
    }
    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Updating associated health check with Shield"


def test_shield_disassociate_health_check(
    clean_db, protection_id, service_instance_id, service_instance, operation_id, shield
):
    service_instance.shield_associated_health_check = {
        "domain_name": "example.com",
        "health_check_id": "example.com ID",
        "protection_id": protection_id,
    }

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    shield.expect_disassociate_health_check(protection_id, "example.com ID")

    disassociate_health_check.call_local(operation_id)

    shield.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.shield_associated_health_check == None
    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Disassociating health check with Shield"


def test_shield_disassociate_health_check_unmigrated_cdn_dedicated_waf_instance(
    clean_db,
    service_instance_id,
    unmigrated_cdn_dedicated_waf_service_instance_operation_id,
    shield,
):
    operation = clean_db.session.get(
        Operation, unmigrated_cdn_dedicated_waf_service_instance_operation_id
    )
    service_instance = operation.service_instance

    disassociate_health_check.call_local(
        unmigrated_cdn_dedicated_waf_service_instance_operation_id
    )

    shield.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.shield_associated_health_check == None


def test_shield_disassociate_health_check_empty_check(
    clean_db, service_instance_id, service_instance, operation_id, shield
):
    service_instance.shield_associated_health_check = {}

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    disassociate_health_check.call_local(operation_id)

    shield.assert_no_pending_responses()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.shield_associated_health_check == {}
