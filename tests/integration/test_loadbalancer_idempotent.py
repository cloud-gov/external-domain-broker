import pytest

from broker.extensions import db
from broker.tasks import alb as alb_tasks

from tests.lib import factories


@pytest.fixture
def service_instance():
    service_instance = factories.ALBServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com", "foo.com"],
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_name="certificate_name",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        private_key_pem="SOMEPRIVATEKEY",
        alb_listener_arn="arn:aws:elasticloadbalancingv2:us-west-1:1234:listener/app/foo/1234/4567",
        alb_arn="arn:aws:elasticloadbalancingv2:us-west-1:1234:loadbalancer/app/foo/1234"
    )
    factories.ChallengeFactory.create(
        domain="example.com",
        validation_contents="example txt",
        service_instance=service_instance,
    )
    factories.ChallengeFactory.create(
        domain="foo.com",
        validation_contents="foo txt",
        service_instance=service_instance,
    )
    db.session.refresh(service_instance)
    return service_instance


@pytest.fixture
def provision_operation(service_instance):
    operation = factories.OperationFactory.create(
        id=4321, service_instance=service_instance
    )
    return operation


def test_select_alb_idempotent_when_provisioning(clean_db, alb, provision_operation, service_instance):
    # the idea here is that the service_instance has alb_listener_arn set and is a provision operation
    # so we should not be calling out to the stubbed ALB.
    # no raised UnStubbedResponseException == idempotent operation
    alb_tasks.select_alb.call_local(4321)
