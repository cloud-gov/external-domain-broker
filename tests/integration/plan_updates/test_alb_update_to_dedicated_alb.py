import pytest
import uuid

from broker.models import DedicatedALBServiceInstance

from tests.lib import factories
from tests.integration.dedicated_alb.test_dedicated_alb_provisioning import (
    subtest_provision_selects_dedicated_alb,
    subtest_provision_adds_certificate_to_alb,
)
from tests.lib.provision import (
    subtest_provision_marks_operation_as_succeeded,
    subtest_provision_waits_for_route53_changes,
)
from tests.lib.alb.provision import subtest_provision_provisions_ALIAS_records
from tests.lib.alb.update import (
    subtest_removes_previous_certificate_from_alb,
)


@pytest.fixture
def organization_guid():
    return str(uuid.uuid4())


@pytest.fixture
def service_instance(clean_db):
    service_instance = factories.ALBServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        alb_arn="alb-arn-1",
        alb_listener_arn="alb-listener-arn-1",
        domain_internal="fake1234.cloud.test",
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
    service_instance.current_certificate = current_cert
    clean_db.session.add(service_instance)
    clean_db.session.add(current_cert)
    clean_db.session.commit()
    clean_db.session.expunge_all()
    return service_instance


def test_update_alb_to_dedicated_alb_happy_path(
    clean_db, client, service_instance, tasks, route53, alb, organization_guid
):
    client.update_instance_to_dedicated_alb("4321", organization_guid=organization_guid)
    assert client.response.status_code == 202, client.response.json
    clean_db.session.expunge_all()
    instance = clean_db.session.get(DedicatedALBServiceInstance, "4321")
    assert instance.org_id == organization_guid
    assert instance is not None
    assert instance.new_certificate is not None
    assert instance.current_certificate is not None
    assert instance.current_certificate is instance.new_certificate
    # path should look like:
    # - pick ALB
    # - add certificate
    # - update DNS
    # - remove certificate from old ALB
    subtest_provision_selects_dedicated_alb(tasks, alb, organization_guid)
    subtest_provision_adds_certificate_to_alb(tasks, alb)
    instance_model = DedicatedALBServiceInstance
    subtest_provision_provisions_ALIAS_records(tasks, route53, instance_model)
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    subtest_renewal_removes_certificate_from_alb(tasks, alb)
    clean_db.session.expunge_all()
    instance = clean_db.session.get(DedicatedALBServiceInstance, "4321")
    assert instance.new_certificate is None
    assert instance.current_certificate is not None
    subtest_provision_marks_operation_as_succeeded(tasks, instance_model)


def subtest_renewal_removes_certificate_from_alb(tasks, alb):
    alb.expect_remove_certificate_from_listener("alb-listener-arn-1", "certificate_arn")

    tasks.run_queued_tasks_and_enqueue_dependents()

    alb.assert_no_pending_responses()
