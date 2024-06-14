import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    CDNDedicatedWAFServiceInstance,
)
from tests.lib.client import check_last_operation_description

from tests.lib.provision import (
    subtest_provision_creates_LE_user,
    subtest_provision_creates_private_key_and_csr,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_answers_challenges,
    subtest_provision_marks_operation_as_succeeded,
)
from tests.lib.cdn.provision import (
    subtest_provision_creates_provision_operation,
    subtest_provision_retrieves_certificate,
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_creates_cloudfront_distribution_with_tags,
    subtest_provision_waits_for_cloudfront_distribution,
    subtest_provision_provisions_ALIAS_records,
)
from tests.lib.cdn.update import (
    subtest_update_happy_path,
    subtest_update_same_domains,
)

# The subtests below are "interesting".  Before test_provision_happy_path, we
# had separate tests for each stage in the task pipeline.  But each test would
# have to duplicate much of the previous test.  This was arduous and slow. Now
# we have a single test_provision_happy_path, and many subtest_foo helper
# methods.  This still makes it clear which stage in the task pipeline is
# failing (look for the subtask_foo in the traceback), and allows us to re-use
# these subtasks when testing failure scenarios.


def test_provision_happy_path(
    client, dns, tasks, route53, iam_commercial, simple_regex, cloudfront, wafv2
):
    instance_model = CDNDedicatedWAFServiceInstance
    operation_id = subtest_provision_creates_provision_operation(
        client, dns, instance_model
    )
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_provision_creates_LE_user(tasks, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Registering user for Lets Encrypt"
    )
    subtest_provision_creates_private_key_and_csr(tasks, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Creating credentials for Lets Encrypt"
    )
    subtest_provision_initiates_LE_challenge(tasks, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Initiating Lets Encrypt challenges"
    )
    subtest_provision_updates_TXT_records(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Updating DNS TXT records"
    )
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for DNS changes"
    )
    subtest_provision_answers_challenges(tasks, dns, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Answering Lets Encrypt challenges"
    )
    subtest_provision_retrieves_certificate(tasks, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Retrieving SSL certificate from Lets Encrypt"
    )
    subtest_provision_uploads_certificate_to_iam(
        tasks, iam_commercial, simple_regex, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Uploading SSL certificate to AWS"
    )
    subtest_provision_create_web_acl(tasks, wafv2)
    check_last_operation_description(
        client, "4321", operation_id, "Creating custom WAFv2 web ACL"
    )
    subtest_provision_creates_cloudfront_distribution_with_tags(
        tasks, cloudfront, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Creating CloudFront distribution"
    )
    subtest_provision_waits_for_cloudfront_distribution(
        tasks, cloudfront, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for CloudFront distribution"
    )
    subtest_provision_provisions_ALIAS_records(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Creating DNS ALIAS records"
    )
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for DNS changes"
    )
    subtest_provision_creates_health_checks(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Creating health checks"
    )
    subtest_provision_marks_operation_as_succeeded(tasks, instance_model)
    check_last_operation_description(client, "4321", operation_id, "Complete!")
    subtest_update_happy_path(
        client,
        dns,
        tasks,
        route53,
        iam_commercial,
        simple_regex,
        cloudfront,
        instance_model,
    )
    subtest_update_same_domains(client, dns, tasks, route53, cloudfront, instance_model)


def subtest_provision_create_web_acl(tasks, wafv2):
    db.session.expunge_all()
    service_instance = db.session.get(CDNDedicatedWAFServiceInstance, "4321")

    wafv2.expect_create_web_acl(
        distribution_id=service_instance.cloudfront_distribution_id,
        rule_group_arn=config.WAF_RATE_LIMIT_RULE_GROUP_ARN,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(CDNDedicatedWAFServiceInstance, "4321")
    assert service_instance.dedicated_waf_web_acl_arn
    assert (
        service_instance.dedicated_waf_web_acl_arn
        == f"arn:aws:wafv2::000000000000:global/webacl/{service_instance.cloudfront_distribution_id}-dedicated-waf"
    )


def subtest_provision_creates_health_checks(tasks, route53, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")

    for domain_name in service_instance.domain_names:
        route53.expect_create_health_check(service_instance.id, domain_name)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.route53_health_check_ids == ["example.com ID", "foo.com ID"]
    route53.assert_no_pending_responses()
