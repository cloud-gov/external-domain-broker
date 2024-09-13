import pytest  # noqa F401

from broker.extensions import db
from broker.models import DedicatedALBServiceInstance
from tests.lib import factories
from tests.lib.client import check_last_operation_description
from tests.lib.alb.deprovision import (
    subtest_deprovision_creates_deprovision_operation,
    subtest_deprovision_removes_ALIAS_records,
    subtest_deprovision_removes_cert_from_alb,
)
from tests.lib.deprovision import (
    subtest_deprovision_removes_TXT_records,
    subtest_deprovision_removes_certificate_from_iam,
    subtest_deprovision_marks_operation_as_succeeded,
)


@pytest.fixture
def service_instance():
    service_instance = factories.DedicatedALBServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com", "foo.com"],
        route53_alias_hosted_zone="ALBHOSTEDZONEID",
        alb_listener_arn="arn:aws:elasticloadbalancingv2:us-west-1:1234:listener/app/foo/1234/4567",
        alb_arn="arn:aws:elasticloadbalancingv2:us-west-1:1234:loadbalancer/app/foo/1234",
        domain_internal="fake1234.cloud.test",
        org_id="our-org",
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


def test_deprovision_happy_path(
    client, service_instance, tasks, route53, iam_govcloud, alb
):
    instance_model = DedicatedALBServiceInstance
    service_instance = db.session.get(instance_model, "1234")
    operation_id = subtest_deprovision_creates_deprovision_operation(
        instance_model, client, service_instance
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
    subtest_deprovision_removes_cert_from_alb(
        instance_model,
        tasks,
        service_instance,
        alb,
    )
    check_last_operation_description(
        client, "1234", operation_id, "Removing SSL certificate from load balancer"
    )
    subtest_deprovision_removes_certificate_from_iam(
        instance_model,
        tasks,
        service_instance,
        iam_govcloud,
    )
    check_last_operation_description(
        client, "1234", operation_id, "Removing SSL certificate from AWS"
    )
    subtest_deprovision_marks_operation_as_succeeded(instance_model, tasks)
    check_last_operation_description(client, "1234", operation_id, "Complete!")
