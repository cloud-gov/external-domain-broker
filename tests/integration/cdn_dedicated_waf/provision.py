import pytest  # noqa F401
import uuid

from broker.extensions import config, db
from broker.models import (
    CDNDedicatedWAFServiceInstance,
)


def subtest_provision_create_web_acl(tasks, wafv2, service_instance_id="4321"):
    db.session.expunge_all()
    service_instance = db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )

    wafv2.expect_create_web_acl(
        service_instance.id,
        config.WAF_RATE_LIMIT_RULE_GROUP_ARN,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance_id
    )
    assert service_instance.dedicated_waf_web_acl_id
    web_acl_name = (
        f"{config.DEDICATED_WAF_NAME_PREFIX}-{service_instance.id}-dedicated-waf"
    )
    assert service_instance.dedicated_waf_web_acl_id == f"{web_acl_name}-id"
    assert service_instance.dedicated_waf_web_acl_name
    assert service_instance.dedicated_waf_web_acl_name == web_acl_name
    assert service_instance.dedicated_waf_web_acl_arn
    assert (
        service_instance.dedicated_waf_web_acl_arn
        == f"arn:aws:wafv2::000000000000:global/webacl/{web_acl_name}"
    )


def subtest_provision_creates_health_checks(
    tasks,
    route53,
    instance_model,
    service_instance_id="4321",
    expected_domain_names=["example.com", "foo.com"],
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    for domain_name in service_instance.domain_names:
        route53.expect_create_health_check(service_instance.id, domain_name)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert sorted(
        service_instance.route53_health_checks,
        key=lambda check: check["domain_name"],
    ) == sorted(
        [
            {"domain_name": domain, "health_check_id": f"{domain} ID"}
            for domain in expected_domain_names
        ],
        key=lambda check: check["domain_name"],
    )
    route53.assert_no_pending_responses()


def subtest_provision_associates_health_checks(
    tasks,
    shield,
    instance_model,
    service_instance_id="4321",
    expected_domain_names=["example.com", "foo.com"],
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    if not service_instance:
        raise Exception("Could not load service instance")

    protection_id = str(uuid.uuid4())
    protection = {
        "Id": protection_id,
        "ResourceArn": service_instance.cloudfront_distribution_arn,
    }
    shield.expect_list_protections([protection])

    for health_check in service_instance.route53_health_checks:
        health_check_id = health_check["health_check_id"]
        shield.expect_associate_health_check(protection_id, health_check_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert service_instance.shield_associated_health_checks == sorted(
        [
            {"health_check_id": f"{domain} ID", "protection_id": protection_id}
            for domain in expected_domain_names
        ],
        key=lambda check: check["health_check_id"],
    )

    shield.assert_no_pending_responses()
