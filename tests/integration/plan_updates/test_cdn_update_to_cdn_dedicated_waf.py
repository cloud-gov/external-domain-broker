import json
import pytest  # noqa F401
import uuid

from broker.extensions import db
from broker.models import (
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
    Operation,
)
from tests.lib import factories
from tests.lib.client import check_last_operation_description

from tests.lib.cdn.update import (
    subtest_update_waits_for_cloudfront_update,
    subtest_update_updates_ALIAS_records,
    subtest_update_same_domains_does_not_create_new_certificate,
    subtest_update_same_domains_does_not_retrieve_new_certificate,
    subtest_update_same_domains_does_not_update_iam,
    subtest_update_same_domains_updates_cloudfront,
    subtest_update_same_domains_does_not_delete_server_certificate,
    subtest_update_same_domains_does_not_create_new_challenges,
    subtest_update_same_domains_does_not_update_route53,
    subtest_update_creates_private_key_and_csr,
    subtest_gets_new_challenges,
    subtest_update_updates_TXT_records,
    subtest_waits_for_dns_changes,
    subtest_update_answers_challenges,
    subtest_update_retrieves_new_cert,
    subtest_update_uploads_new_cert,
    subtest_updates_cloudfront,
    subtest_update_waits_for_cloudfront_update,
    subtest_update_updates_ALIAS_records,
    subtest_waits_for_dns_changes,
    subtest_update_removes_certificate_from_iam,
    subtest_update_marks_update_complete,
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
from tests.integration.cdn_dedicated_waf.update import (
    subtest_update_web_acl_does_not_update,
    subtest_updates_health_checks,
    subtest_updates_associated_health_checks,
)


@pytest.fixture
def service_instance_id():
    return str(uuid.uuid4())


@pytest.fixture
def service_instance(service_instance_id):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_distribution_arn="fake-resource-arn",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        forward_cookie_policy=CDNServiceInstance.ForwardCookiePolicy.ALL.value,
        origin_protocol_policy="https-only",
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
        csr_pem="SOMECSRPEM",
        order_json=json.dumps({"foo": "bar"}),
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

    db.session.add(current_cert)
    db.session.add(service_instance)

    db.session.commit()
    db.session.expunge_all()
    return service_instance


def test_update_plan_only(
    client,
    service_instance_id,
    tasks,
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
    subtest_update_same_domains_does_not_create_new_certificate(
        tasks,
        instance_model,
        service_instance_id=service_instance_id,
        expected_num_certificates=1,
    )
    subtest_update_same_domains_does_not_create_new_challenges(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_same_domains_does_not_update_route53(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_same_domains_does_not_retrieve_new_certificate(tasks)
    subtest_update_same_domains_does_not_update_iam(tasks)
    subtest_provision_create_web_acl(
        tasks, wafv2, service_instance_id=service_instance_id
    )
    subtest_update_same_domains_updates_cloudfront(
        tasks,
        cloudfront,
        instance_model,
        service_instance_id=service_instance_id,
        expect_update_domain_names=["example.com", "foo.com"],
        expect_forwarded_headers=[],
        expect_forward_cookie_policy=CDNServiceInstance.ForwardCookiePolicy.ALL.value,
        expect_forwarded_cookies=[],
        expect_origin_hostname="origin_hostname",
        expect_origin_path="origin_path",
        expect_origin_protocol_policy="https-only",
    )
    subtest_update_waits_for_cloudfront_update(
        tasks, cloudfront, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_updates_ALIAS_records(
        tasks,
        route53,
        instance_model,
        service_instance_id=service_instance_id,
        expected_domains=["example.com", "foo.com"],
    )
    subtest_waits_for_dns_changes(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_same_domains_does_not_delete_server_certificate(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    subtest_provision_creates_health_checks(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    subtest_provision_associates_health_checks(
        tasks, shield, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_marks_update_complete(
        tasks, instance_model, service_instance_id=service_instance_id
    )


def test_update_plan_and_domains(
    client,
    service_instance_id,
    tasks,
    route53,
    cloudfront,
    wafv2,
    shield,
    dns,
    iam_commercial,
    simple_regex,
    service_instance,
):
    instance_model = CDNDedicatedWAFServiceInstance
    operation_id = subtest_update_creates_update_plan_and_domains_operation(
        client, dns, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Queuing tasks"
    )
    subtest_update_creates_private_key_and_csr(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    subtest_gets_new_challenges(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_updates_TXT_records(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    subtest_waits_for_dns_changes(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_answers_challenges(
        tasks, dns, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_retrieves_new_cert(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_uploads_new_cert(tasks, iam_commercial, simple_regex, instance_model)
    subtest_update_web_acl_does_not_update(tasks, wafv2)
    subtest_updates_cloudfront(
        tasks, cloudfront, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_waits_for_cloudfront_update(
        tasks, cloudfront, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_updates_ALIAS_records(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    subtest_waits_for_dns_changes(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    subtest_update_removes_certificate_from_iam(
        tasks, iam_commercial, instance_model, service_instance_id=service_instance_id
    )
    subtest_updates_health_checks(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Updating health checks"
    )
    subtest_updates_associated_health_checks(
        tasks, shield, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Updating associated health checks with Shield",
    )
    subtest_update_marks_update_complete(
        tasks, instance_model, service_instance_id=service_instance_id
    )


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


def subtest_update_creates_update_plan_and_domains_operation(
    client, dns, instance_model, service_instance_id="4321"
):
    dns.add_cname("_acme-challenge.foo.com")
    dns.add_cname("_acme-challenge.bar.com")
    client.update_cdn_to_cdn_dedicated_waf_instance(
        service_instance_id,
        params={
            "domains": "bar.com, Foo.com",
            "origin": "new-origin.com",
            "path": "/somewhere-else",
            "forward_cookies": "mycookie,myothercookie, anewcookie",
            "forward_headers": "x-my-header, x-your-header   ",
            "insecure_origin": True,
        },
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == service_instance_id

    instance = db.session.get(instance_model, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "new-origin.com"
    assert instance.cloudfront_origin_path == "/somewhere-else"
    return operation_id
