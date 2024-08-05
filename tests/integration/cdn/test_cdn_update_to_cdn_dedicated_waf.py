import pytest  # noqa F401
import uuid

from broker.extensions import db
from broker.models import CDNDedicatedWAFServiceInstance, Operation
from tests.lib import factories
from tests.lib.client import check_last_operation_description

from tests.lib.cdn.update import (
    subtest_update_waits_for_cloudfront_update,
    subtest_update_updates_ALIAS_records,
    subtest_update_same_domains_creates_update_operation,
    subtest_update_same_domains_does_not_create_new_certificate,
    subtest_update_same_domains_does_not_retrieve_new_certificate,
    subtest_update_same_domains_does_not_update_iam,
    subtest_update_same_domains_updates_cloudfront,
    subtest_update_same_domains_does_not_delete_server_certificate,
    subtest_update_same_domains_does_not_create_new_challenges,
    subtest_update_same_domains_does_not_update_route53,
)
from tests.lib.update import (
    subtest_waits_for_dns_changes,
    subtest_update_marks_update_complete,
)
from tests.integration.cdn_dedicated_waf.provision import (
    subtest_provision_create_web_acl,
    subtest_provision_creates_health_checks,
    subtest_provision_associates_health_checks,
)


@pytest.fixture
def service_instance_id():
    return str(uuid.uuid4())


@pytest.fixture
def service_instance(service_instance_id):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
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


def test_update_plan_only(
    client,
    service_instance_id,
    tasks,
    dns,
    route53,
    cloudfront,
    wafv2,
    shield,
    service_instance,
):
    operation_id = subtest_creates_update_plan_operation(client, service_instance_id)
    check_last_operation_description(
        client, service_instance_id, operation_id, "Queuing tasks"
    )
    instance_model = CDNDedicatedWAFServiceInstance
    subtest_update_same_domains_creates_update_operation(client, dns, instance_model)
    subtest_update_same_domains_does_not_create_new_certificate(tasks, instance_model)
    subtest_update_same_domains_does_not_create_new_challenges(tasks, instance_model)
    subtest_update_same_domains_does_not_update_route53(tasks, route53, instance_model)
    subtest_update_same_domains_does_not_retrieve_new_certificate(tasks, instance_model)
    subtest_update_same_domains_does_not_update_iam(tasks, instance_model)
    subtest_provision_create_web_acl(
        tasks, wafv2, service_instance_id=service_instance_id
    )
    subtest_update_same_domains_updates_cloudfront(tasks, cloudfront, instance_model)
    subtest_update_waits_for_cloudfront_update(tasks, cloudfront, instance_model)
    subtest_update_updates_ALIAS_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_same_domains_does_not_delete_server_certificate(
        tasks, instance_model
    )
    subtest_provision_creates_health_checks(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    subtest_provision_associates_health_checks(
        tasks, shield, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_marks_update_complete(tasks, instance_model)


def subtest_creates_update_plan_operation(client, service_instance_id):
    client.update_cdn_to_cdn_dedicated_waf_instance(service_instance_id)
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == service_instance_id

    return operation_id
