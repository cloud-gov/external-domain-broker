import pytest
import uuid
import random

from broker.tasks.shield import associate_health_check, update_associated_health_check
from broker.models import CDNDedicatedWAFServiceInstance

from tests.lib import factories


@pytest.fixture
def service_instance_id():
    return str(random.randrange(0, 10000))


@pytest.fixture
def protection_id():
    return str(uuid.uuid4())


@pytest.fixture
def service_instance(clean_db, service_instance_id):
    service_instance = factories.CDNDedicatedWAFServiceInstanceFactory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_distribution_arn="fake-distribution-arn",
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
    clean_db.session.add(service_instance)
    clean_db.session.add(current_cert)
    clean_db.session.add(new_cert)
    clean_db.session.commit()
    clean_db.session.expunge_all()
    factories.OperationFactory.create(
        id=service_instance_id, service_instance=service_instance
    )
    return service_instance


@pytest.fixture
def protection(protection_id, service_instance):
    return {
        "Id": protection_id,
        "ResourceArn": service_instance.cloudfront_distribution_arn,
    }


def test_shield_update_no_change_associated_health_check(
    clean_db, protection, service_instance_id, service_instance, shield
):
    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    shield.expect_list_protections([protection])

    # simulate a change in domain names to ["example.com", "foo.com"]
    service_instance.domain_names = ["example.com", "bar.com"]
    service_instance.route53_health_checks = [
        {"domain_name": "example.com", "health_check_id": "example.com ID"},
        {"domain_name": "bar.com", "health_check_id": "bar.com ID"},
    ]
    service_instance.shield_associated_health_check = {
        "domain_name": "example.com",
        "health_check_id": "example.com ID",
    }
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    update_associated_health_check.call_local(service_instance_id)

    # There should be no calls to associate or disassociate a health check with Shield
    shield.assert_no_pending_responses()


def test_shield_update_change_associated_health_check(
    clean_db, protection_id, protection, service_instance_id, service_instance, shield
):
    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )

    shield.expect_list_protections([protection])

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
    }

    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    shield.expect_disassociate_health_check(protection_id, "example.com ID")
    shield.expect_associate_health_check(protection_id, "bar.com ID")

    update_associated_health_check.call_local(service_instance_id)

    shield.assert_no_pending_responses()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.shield_associated_health_check == {
        "domain_name": "bar.com",
        "health_check_id": "bar.com ID",
    }
