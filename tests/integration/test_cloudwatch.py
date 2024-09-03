import pytest
import uuid
import random

from botocore.exceptions import WaiterError

from broker.tasks.cloudwatch import (
    create_health_check_alarms,
)
from broker.extensions import config
from broker.models import Operation

from tests.lib import factories


@pytest.fixture
def service_instance_id():
    return str(random.randrange(0, 10000))


@pytest.fixture
def operation_id():
    return str(random.randrange(0, 10000))


@pytest.fixture
def cloudfront_distribution_arn():
    return str(uuid.uuid4())


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
        id=operation_id, service_instance=service_instance
    )
    return service_instance


def test_create_health_check_alarms(
    clean_db,
    service_instance,
    operation_id,
    cloudwatch_commercial,
):

    tags = service_instance.tags if service_instance.tags else []

    for health_check in service_instance.route53_health_checks:
        health_check_id = health_check["health_check_id"]
        alarm_name = f"{config.CLOUDWATCH_ALARM_NAME_PREFIX}-{health_check_id}"

        cloudwatch_commercial.expect_put_metric_alarm(health_check_id, alarm_name, tags)
        cloudwatch_commercial.expect_describe_alarms(
            alarm_name, [{"AlarmArn": str(uuid.uuid4())}]
        )
        cloudwatch_commercial.expect_describe_alarms(
            alarm_name, [{"AlarmArn": str(uuid.uuid4())}]
        )

    create_health_check_alarms.call_local(operation_id)

    # asserts that all the mocked calls above were made
    cloudwatch_commercial.assert_no_pending_responses()

    clean_db.session.expunge_all()

    operation = clean_db.session.get(Operation, operation_id)
    assert (
        operation.step_description
        == "Creating Cloudwatch alarms for Route53 health checks"
    )


def test_create_health_check_alarm_waits(
    clean_db,
    service_instance,
    operation_id,
    cloudwatch_commercial,
):
    tags = service_instance.tags if service_instance.tags else []

    health_check_id = service_instance.route53_health_checks[0]["health_check_id"]
    alarm_name = f"{config.CLOUDWATCH_ALARM_NAME_PREFIX}-{health_check_id}"

    cloudwatch_commercial.expect_put_metric_alarm(health_check_id, alarm_name, tags)
    # waiting for alarm to exist
    cloudwatch_commercial.expect_describe_alarms(alarm_name, [])
    cloudwatch_commercial.expect_describe_alarms(alarm_name, [])
    cloudwatch_commercial.expect_describe_alarms(
        alarm_name, [{"AlarmArn": str(uuid.uuid4())}]
    )
    # one final call to get the alarm ARN
    cloudwatch_commercial.expect_describe_alarms(
        alarm_name, [{"AlarmArn": str(uuid.uuid4())}]
    )

    health_check_id = service_instance.route53_health_checks[1]["health_check_id"]
    alarm_name = f"{config.CLOUDWATCH_ALARM_NAME_PREFIX}-{health_check_id}"

    cloudwatch_commercial.expect_put_metric_alarm(health_check_id, alarm_name, tags)
    # waiting for alarm to exist
    cloudwatch_commercial.expect_describe_alarms(
        alarm_name, [{"AlarmArn": str(uuid.uuid4())}]
    )
    # one final call to get the alarm ARN
    cloudwatch_commercial.expect_describe_alarms(
        alarm_name, [{"AlarmArn": str(uuid.uuid4())}]
    )

    create_health_check_alarms.call_local(operation_id)

    # asserts that all the mocked calls above were made
    cloudwatch_commercial.assert_no_pending_responses()


def test_create_health_check_alarm_error_on_multiple_alarms_found(
    service_instance,
    operation_id,
    cloudwatch_commercial,
):
    tags = service_instance.tags if service_instance.tags else []

    health_check_id = service_instance.route53_health_checks[0]["health_check_id"]
    alarm_name = f"{config.CLOUDWATCH_ALARM_NAME_PREFIX}-{health_check_id}"

    cloudwatch_commercial.expect_put_metric_alarm(health_check_id, alarm_name, tags)
    # waiting for alarm to exist
    cloudwatch_commercial.expect_describe_alarms(
        alarm_name, [{"AlarmArn": str(uuid.uuid4())}, {"AlarmArn": str(uuid.uuid4())}]
    )
    # one final call to get the alarm ARN
    cloudwatch_commercial.expect_describe_alarms(
        alarm_name, [{"AlarmArn": str(uuid.uuid4())}, {"AlarmArn": str(uuid.uuid4())}]
    )

    with pytest.raises(RuntimeError):
        create_health_check_alarms.call_local(operation_id)

    # asserts that all the mocked calls above were made
    cloudwatch_commercial.assert_no_pending_responses()


def test_create_health_check_alarm_error_if_alarm_not_found(
    service_instance,
    operation_id,
    cloudwatch_commercial,
):
    tags = service_instance.tags if service_instance.tags else []

    health_check_id = service_instance.route53_health_checks[0]["health_check_id"]
    alarm_name = f"{config.CLOUDWATCH_ALARM_NAME_PREFIX}-{health_check_id}"

    cloudwatch_commercial.expect_put_metric_alarm(health_check_id, alarm_name, tags)
    # waiting for alarm to exist
    for i in list(range(config.AWS_POLL_MAX_ATTEMPTS)):
        cloudwatch_commercial.expect_describe_alarms(alarm_name, [])

    with pytest.raises(WaiterError):
        create_health_check_alarms.call_local(operation_id)

    # asserts that all the mocked calls above were made
    cloudwatch_commercial.assert_no_pending_responses()
