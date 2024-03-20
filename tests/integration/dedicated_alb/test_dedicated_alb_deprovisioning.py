import pytest  # noqa F401

from broker.extensions import db
from broker.models import Operation, DedicatedALBServiceInstance
from tests.lib import factories
from tests.lib.client import check_last_operation_description


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


def test_refuses_to_deprovision_synchronously(client, service_instance):
    client.deprovision_dedicated_alb_instance("1234", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_deprovision_synchronously_by_default(client, service_instance):
    client.deprovision_dedicated_alb_instance("1234", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_deprovision_happy_path(
    client, service_instance, dns, tasks, route53, iam_govcloud, simple_regex, alb
):
    service_instance = DedicatedALBServiceInstance.query.get("1234")
    operation_id = subtest_deprovision_creates_deprovision_operation(
        client, service_instance
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
    subtest_deprovision_removes_cert_from_alb(tasks, service_instance, alb)
    check_last_operation_description(
        client, "1234", operation_id, "Removing SSL certificate from load balancer"
    )
    subtest_deprovision_removes_certificate_from_iam(
        tasks, service_instance, iam_govcloud
    )
    check_last_operation_description(
        client, "1234", operation_id, "Removing SSL certificate from AWS"
    )
    subtest_deprovision_marks_operation_as_succeeded(tasks)
    check_last_operation_description(client, "1234", operation_id, "Complete!")


def subtest_deprovision_creates_deprovision_operation(client, service_instance):
    service_instance = DedicatedALBServiceInstance.query.get("1234")
    client.deprovision_dedicated_alb_instance(
        service_instance.id, accepts_incomplete="true"
    )

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = Operation.query.get(operation_id)

    assert operation is not None
    assert operation.state == Operation.States.IN_PROGRESS.value
    assert operation.action == Operation.Actions.DEPROVISION.value
    assert operation.service_instance_id == service_instance.id

    return operation_id


def subtest_deprovision_removes_ALIAS_records(tasks, route53):
    route53.expect_remove_ALIAS(
        "example.com.domains.cloud.test", "fake1234.cloud.test", "ALBHOSTEDZONEID"
    )
    route53.expect_remove_ALIAS(
        "foo.com.domains.cloud.test", "fake1234.cloud.test", "ALBHOSTEDZONEID"
    )

    # one for marking provisioning tasks canceled, which is tested elsewhere
    tasks.run_queued_tasks_and_enqueue_dependents()
    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_removes_TXT_records(tasks, route53):
    route53.expect_remove_TXT(
        "_acme-challenge.example.com.domains.cloud.test", "example txt"
    )
    route53.expect_remove_TXT("_acme-challenge.foo.com.domains.cloud.test", "foo txt")

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()


def subtest_deprovision_removes_cert_from_alb(tasks, service_instance, alb):
    service_instance = DedicatedALBServiceInstance.query.get("1234")
    alb.expect_remove_certificate_from_listener(
        service_instance.alb_listener_arn,
        service_instance.current_certificate.iam_server_certificate_arn,
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()


def subtest_deprovision_removes_certificate_from_iam(
    tasks, service_instance, iam_govcloud
):
    service_instance = DedicatedALBServiceInstance.query.get("1234")
    iam_govcloud.expects_delete_server_certificate(
        service_instance.new_certificate.iam_server_certificate_name
    )
    iam_govcloud.expects_delete_server_certificate(
        service_instance.current_certificate.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam_govcloud.assert_no_pending_responses()


def subtest_deprovision_removes_certificate_from_iam_when_missing(
    tasks, service_instance, iam_govcloud
):
    service_instance = DedicatedALBServiceInstance.query.get("1234")
    iam_govcloud.expects_delete_server_certificate_returning_no_such_entity(
        name=service_instance.iam_server_certificate_name
    )
    tasks.run_queued_tasks_and_enqueue_dependents()
    iam_govcloud.assert_no_pending_responses()


def subtest_deprovision_marks_operation_as_succeeded(tasks):
    db.session.expunge_all()
    service_instance = DedicatedALBServiceInstance.query.get("1234")
    assert not service_instance.deactivated_at

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = DedicatedALBServiceInstance.query.get("1234")
    assert service_instance.deactivated_at

    operation = service_instance.operations.first()
    assert operation.state == "succeeded"
