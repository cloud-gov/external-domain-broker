import pytest

from broker.tasks.sns import create_notification_topic, delete_notification_topic
from broker.models import Operation, CDNDedicatedWAFServiceInstance

from tests.lib import factories


@pytest.fixture
def service_instance(
    clean_db,
    operation_id,
    service_instance_id,
    cloudfront_distribution_arn,
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
            {
                "domain_name": "example.com",
                "health_check_id": "example.com ID",
            },
            {
                "domain_name": "foo.com",
                "health_check_id": "foo.com ID",
            },
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
    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )
    return service_instance


def test_create_sns_notification_topic(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    sns_commercial,
):
    sns_commercial.expect_create_topic(service_instance)

    create_notification_topic.call_local(operation_id)

    sns_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()

    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Creating SNS notification topic"
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )
    assert (
        service_instance.sns_notification_topic_arn
        == f"{service_instance.id}-notifications-arn"
    )


def test_create_sns_notification_topic_with_tags(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    sns_commercial,
):
    tags = [{"Key": "foo", "Value": "bar"}]
    service_instance.tags = tags
    clean_db.session.add(service_instance)
    clean_db.session.commit()

    sns_commercial.expect_create_topic(service_instance)

    create_notification_topic.call_local(operation_id)

    sns_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )
    assert (
        service_instance.sns_notification_topic_arn
        == f"{service_instance.id}-notifications-arn"
    )


def test_create_sns_notification_topic_unmigrated_instance(
    clean_db,
    service_instance_id,
    unmigrated_cdn_service_instance_operation_id,
    sns_commercial,
):
    operation = clean_db.session.get(
        Operation, unmigrated_cdn_service_instance_operation_id
    )
    service_instance = operation.service_instance

    assert service_instance.sns_notification_topic_arn == None

    sns_commercial.expect_create_topic(service_instance)

    create_notification_topic.call_local(unmigrated_cdn_service_instance_operation_id)

    sns_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )
    assert (
        service_instance.sns_notification_topic_arn
        == f"{service_instance.id}-notifications-arn"
    )


def test_delete_sns_notification_topic(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    sns_commercial,
):
    service_instance.sns_notification_topic_arn = "fake-arn"
    clean_db.session.add(service_instance)
    clean_db.session.commit()

    sns_commercial.expect_delete_topic(service_instance.sns_notification_topic_arn)

    clean_db.session.expunge_all()

    delete_notification_topic.call_local(operation_id)

    sns_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()

    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Deleting SNS notification topic"
    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )
    assert service_instance.sns_notification_topic_arn == None


def test_delete_sns_notification_topic_no_value(
    clean_db,
    service_instance,
    operation_id,
    sns_commercial,
):
    service_instance.sns_notification_topic_arn = None
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    delete_notification_topic.call_local(operation_id)

    sns_commercial.assert_no_pending_responses()


def test_delete_sns_notification_topic_not_found(
    clean_db,
    service_instance_id,
    service_instance,
    operation_id,
    sns_commercial,
):
    service_instance.sns_notification_topic_arn = "fake-arn"
    clean_db.session.add(service_instance)
    clean_db.session.commit()

    sns_commercial.expect_delete_topic_not_found(
        service_instance.sns_notification_topic_arn
    )

    clean_db.session.expunge_all()

    delete_notification_topic.call_local(operation_id)

    sns_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )
    assert service_instance.sns_notification_topic_arn == None


def test_delete_sns_notification_topic_unmigrated_instance(
    clean_db,
    service_instance_id,
    unmigrated_cdn_service_instance_operation_id,
    sns_commercial,
):
    operation = clean_db.session.get(
        Operation, unmigrated_cdn_service_instance_operation_id
    )
    service_instance = operation.service_instance

    service_instance.sns_notification_topic_arn = "fake-arn"
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    sns_commercial.expect_delete_topic("fake-arn")

    delete_notification_topic.call_local(unmigrated_cdn_service_instance_operation_id)

    sns_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance,
        service_instance_id,
    )
    assert service_instance.sns_notification_topic_arn == None
