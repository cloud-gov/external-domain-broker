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
    subtest_provision_creates_cloudfront_distribution,
    subtest_provision_waits_for_cloudfront_distribution,
    subtest_provision_provisions_ALIAS_records,
)
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
from tests.lib.cdn.update import (
    subtest_update_creates_update_operation,
    subtest_update_uploads_new_cert,
    subtest_updates_cloudfront,
    subtest_update_waits_for_cloudfront_update,
    subtest_update_updates_ALIAS_records,
    subtest_update_same_domains_creates_update_operation,
    subtest_update_same_domains_does_not_create_new_certificate,
    subtest_update_same_domains_does_not_retrieve_new_certificate,
    subtest_update_same_domains_does_not_update_iam,
    subtest_update_same_domains_updates_cloudfront,
    subtest_update_same_domains_does_not_delete_server_certificate,
    subtest_update_same_domains_does_not_create_new_challenges,
    subtest_update_does_not_create_new_TXT_records,
    subtest_update_does_not_remove_old_TXT_records,
    subtest_update_removes_old_DNS_records,
)
from tests.integration.cdn_dedicated_waf.provision import (
    subtest_provision_create_web_acl,
    subtest_provision_put_web_acl_logging_configuration,
    subtest_provision_creates_health_checks,
    subtest_provision_associate_health_check,
    subtest_provision_creates_health_check_alarms,
    subtest_provision_creates_sns_notification_topic,
    subtest_provision_creates_ddos_detected_alarm,
    subtest_provision_subscribes_sns_notification_topic,
)
from tests.integration.cdn_dedicated_waf.update import (
    subtest_update_web_acl_does_not_update,
    subtest_updates_health_checks_do_not_change,
    subtest_updates_associated_health_check,
    subtest_updates_associated_health_check_no_change,
    subtest_update_creates_new_health_checks,
    subtest_update_deletes_unused_health_checks,
    subtest_update_deletes_health_check_alarms,
    subtest_update_creates_health_check_alarms,
    subtest_update_does_not_create_sns_notification_topic,
    subtest_update_does_not_create_ddos_cloudwatch_alarm,
    subtest_update_unsubscribe_sns_notification_topic,
)


# The subtests below are "interesting".  Before test_provision_happy_path, we
# had separate tests for each stage in the task pipeline.  But each test would
# have to duplicate much of the previous test.  This was arduous and slow. Now
# we have a single test_provision_happy_path, and many subtest_foo helper
# methods.  This still makes it clear which stage in the task pipeline is
# failing (look for the subtask_foo in the traceback), and allows us to re-use
# these subtasks when testing failure scenarios.


def test_provision_happy_path(
    client,
    dns,
    tasks,
    route53,
    iam_commercial,
    simple_regex,
    cloudfront,
    wafv2_commercial,
    shield,
    cloudwatch_commercial,
    sns_commercial,
    organization_guid,
    space_guid,
    mocked_cf_api,
):
    instance_model = CDNDedicatedWAFServiceInstance
    operation_id = subtest_provision_creates_provision_operation(
        client, dns, organization_guid, space_guid, instance_model
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
    subtest_provision_create_web_acl(tasks, wafv2_commercial, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Creating custom WAFv2 web ACL"
    )
    subtest_provision_put_web_acl_logging_configuration(
        tasks, wafv2_commercial, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Updating WAFv2 web ACL logging configuration"
    )
    subtest_provision_creates_cloudfront_distribution(tasks, cloudfront, instance_model)
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
    subtest_provision_creates_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Creating SNS notification topic"
    )
    subtest_provision_subscribes_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Subscribing to SNS notification topic"
    )
    subtest_provision_creates_health_checks(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Creating new health checks"
    )
    subtest_provision_associate_health_check(tasks, shield, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Associating health check with Shield"
    )
    subtest_provision_creates_health_check_alarms(
        tasks, cloudwatch_commercial, instance_model
    )
    check_last_operation_description(
        client,
        "4321",
        operation_id,
        "Creating Cloudwatch alarms for Route53 health checks",
    )
    subtest_provision_creates_ddos_detected_alarm(
        tasks, cloudwatch_commercial, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Creating DDoS detection alarm"
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
        wafv2_commercial,
        shield,
        cloudwatch_commercial,
        sns_commercial,
        instance_model,
    )
    subtest_update_same_domains(
        client,
        dns,
        tasks,
        route53,
        cloudfront,
        wafv2_commercial,
        shield,
        cloudwatch_commercial,
        sns_commercial,
        instance_model,
    )


def subtest_update_happy_path(
    client,
    dns,
    tasks,
    route53,
    iam_commercial,
    simple_regex,
    cloudfront,
    wafv2,
    shield,
    cloudwatch_commercial,
    sns_commercial,
    instance_model,
):
    operation_id = subtest_update_creates_update_operation(client, dns, instance_model)
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
    subtest_update_uploads_new_cert(tasks, iam_commercial, simple_regex, instance_model)
    subtest_update_web_acl_does_not_update(tasks, wafv2)
    subtest_provision_put_web_acl_logging_configuration(tasks, wafv2, instance_model)
    subtest_updates_cloudfront(tasks, cloudfront, instance_model)
    subtest_update_waits_for_cloudfront_update(tasks, cloudfront, instance_model)
    subtest_update_updates_ALIAS_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_removes_certificate_from_iam(tasks, iam_commercial, instance_model)
    subtest_update_does_not_create_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    subtest_update_unsubscribe_sns_notification_topic(
        tasks, sns_commercial, instance_model, service_instance_id="4321"
    )
    subtest_provision_subscribes_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    subtest_update_creates_new_health_checks(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Creating new health checks"
    )
    subtest_updates_associated_health_check(tasks, shield, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Updating associated health check with Shield"
    )
    subtest_update_deletes_unused_health_checks(tasks, route53, instance_model)
    check_last_operation_description(
        client, "4321", operation_id, "Deleting unused health checks"
    )
    subtest_update_deletes_health_check_alarms(
        tasks,
        cloudwatch_commercial,
        instance_model,
        ["example.com ID", "foo.com ID"],
    )
    check_last_operation_description(
        client,
        "4321",
        operation_id,
        "Deleting Cloudwatch alarms for Route53 health checks",
    )
    subtest_update_creates_health_check_alarms(
        tasks, cloudwatch_commercial, instance_model
    )
    check_last_operation_description(
        client,
        "4321",
        operation_id,
        "Creating Cloudwatch alarms for Route53 health checks",
    )
    subtest_update_does_not_create_ddos_cloudwatch_alarm(
        tasks, cloudwatch_commercial, instance_model
    )
    check_last_operation_description(
        client, "4321", operation_id, "Creating DDoS detection alarm"
    )
    subtest_update_marks_update_complete(tasks, instance_model)


def subtest_update_same_domains(
    client,
    dns,
    tasks,
    route53,
    cloudfront,
    wafv2,
    shield,
    cloudwatch_commercial,
    sns_commercial,
    instance_model,
):
    subtest_update_same_domains_creates_update_operation(client, dns, instance_model)
    subtest_update_same_domains_does_not_create_new_certificate(tasks, instance_model)
    subtest_update_same_domains_does_not_create_new_challenges(tasks, instance_model)
    subtest_update_does_not_create_new_TXT_records(tasks, route53, instance_model)
    subtest_update_does_not_remove_old_TXT_records(tasks, route53)
    subtest_update_same_domains_does_not_retrieve_new_certificate(tasks)
    subtest_update_same_domains_does_not_update_iam(tasks)
    subtest_update_web_acl_does_not_update(tasks, wafv2)
    subtest_provision_put_web_acl_logging_configuration(tasks, wafv2, instance_model)
    subtest_update_same_domains_updates_cloudfront(
        tasks,
        cloudfront,
        instance_model,
        expect_update_domain_names=["bar.com", "foo.com"],
    )
    subtest_update_waits_for_cloudfront_update(tasks, cloudfront, instance_model)
    subtest_update_updates_ALIAS_records(tasks, route53, instance_model)
    subtest_waits_for_dns_changes(tasks, route53, instance_model)
    subtest_update_same_domains_does_not_delete_server_certificate(
        tasks, instance_model
    )
    subtest_update_does_not_create_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    subtest_update_unsubscribe_sns_notification_topic(
        tasks, sns_commercial, instance_model, service_instance_id="4321"
    )
    subtest_provision_subscribes_sns_notification_topic(
        tasks, sns_commercial, instance_model
    )
    subtest_updates_health_checks_do_not_change(tasks, route53, instance_model)
    subtest_updates_associated_health_check_no_change(tasks, shield, instance_model)
    subtest_updates_health_checks_do_not_change(tasks, route53, instance_model)
    subtest_update_deletes_health_check_alarms(
        tasks,
        cloudwatch_commercial,
        instance_model,
        ["bar.com ID", "foo.com ID"],
    )
    subtest_update_creates_health_check_alarms(
        tasks, cloudwatch_commercial, instance_model
    )
    subtest_update_does_not_create_ddos_cloudwatch_alarm(
        tasks, cloudwatch_commercial, instance_model
    )
    subtest_update_marks_update_complete(tasks, instance_model)
