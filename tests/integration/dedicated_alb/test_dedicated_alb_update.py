from datetime import date

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    DedicatedALB,
    Operation,
    DedicatedALBServiceInstance,
)

from tests.lib.client import check_last_operation_description

from tests.lib.update import (
    subtest_update_creates_private_key_and_csr,
    subtest_gets_new_challenges,
    subtest_update_creates_new_TXT_records,
    subtest_update_answers_challenges,
    subtest_waits_for_dns_changes,
    subtest_update_retrieves_new_cert,
    subtest_update_marks_update_complete,
    subtest_update_removes_certificate_from_iam,
)
from tests.lib.alb.update import (
    subtest_update_uploads_new_cert,
    subtest_update_provisions_ALIAS_records,
    subtest_removes_previous_certificate_from_alb,
    subtest_update_removes_old_DNS_records,
)


def subtest_update_happy_path(
    client,
    dns,
    tasks,
    route53,
    iam_govcloud,
    simple_regex,
    alb,
    wafv2_govcloud,
    dedicated_alb_id,
):
    instance_model = DedicatedALBServiceInstance
    operation_id = subtest_update_creates_update_operation(client, dns)
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_update_creates_private_key_and_csr(tasks, instance_model)
    subtest_gets_new_challenges(tasks, instance_model)
    subtest_update_creates_new_TXT_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_removes_old_DNS_records(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Removing old DNS records"
    )
    subtest_update_answers_challenges(tasks, dns, instance_model)
    subtest_update_retrieves_new_cert(tasks, instance_model)
    subtest_update_uploads_new_cert(tasks, iam_govcloud, simple_regex, instance_model)
    subtest_update_selects_alb(tasks, alb)
    subtest_update_adds_certificate_to_alb(tasks, alb)
    subtest_update_does_not_create_alb_web_acl(tasks, wafv2_govcloud)
    subtest_update_puts_alb_web_acl_logging_configuration(
        tasks, wafv2_govcloud, dedicated_alb_id
    )
    subtest_update_provisions_ALIAS_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_removes_previous_certificate_from_alb(
        tasks,
        alb,
        "our-arn-0",
        f"arn:aws:iam::000000000000:server-certificate/alb/external-domains-test/4321-{date.today().isoformat()}-1",
    )
    subtest_update_removes_certificate_from_iam(tasks, iam_govcloud, instance_model)
    subtest_update_marks_update_complete(tasks, instance_model)


def subtest_update_creates_update_operation(client, dns):
    dns.add_cname("_acme-challenge.foo.com")
    dns.add_cname("_acme-challenge.bar.com")
    client.update_dedicated_alb_instance("4321", params={"domains": "bar.com, Foo.com"})
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == "4321"

    instance = db.session.get(
        DedicatedALBServiceInstance, operation.service_instance_id
    )
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    return operation_id


def subtest_update_selects_alb(tasks, alb):
    db.session.expunge_all()
    alb.expect_get_certificates_for_listener("our-arn-0", 1)
    alb.expect_get_certificates_for_listener("our-arn-1", 5)
    alb.expect_get_listeners("our-arn-0", "alb-our-arn-0")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.alb_arn.startswith("alb-our-arn-0")


def subtest_update_adds_certificate_to_alb(tasks, alb):
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    certificate = service_instance.new_certificate
    id_ = certificate.id
    alb.expect_add_certificate_to_listener(
        "our-arn-0", certificate.iam_server_certificate_arn
    )
    alb.expect_describe_alb("alb-our-arn-0", "alb.cloud.test")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")

    assert service_instance.new_certificate is None
    assert service_instance.current_certificate is not None
    assert service_instance.current_certificate.id == id_


def subtest_update_does_not_create_alb_web_acl(tasks, wafv2_govcloud):
    tasks.run_queued_tasks_and_enqueue_dependents()
    wafv2_govcloud.assert_no_pending_responses()


def subtest_update_puts_alb_web_acl_logging_configuration(
    tasks, wafv2_govcloud, dedicated_alb_id
):
    dedicated_alb = db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )

    db.session.add(dedicated_alb)
    db.session.commit()

    wafv2_govcloud.expect_put_logging_configuration(
        dedicated_alb.dedicated_waf_web_acl_arn,
        config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    wafv2_govcloud.assert_no_pending_responses()
