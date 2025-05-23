from broker.extensions import db
from broker.models import (
    DedicatedALBServiceInstance,
    CDNDedicatedWAFServiceInstance,
    MigrateDedicatedALBToCDNDedicatedWafServiceInstance,
    Operation,
    ServiceInstanceTypes,
)

from tests.lib.client import check_last_operation_description

from tests.lib.provision import (
    subtest_provision_initiates_LE_challenge,
    subtest_provision_answers_challenges,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
)
from tests.lib.update import (
    subtest_update_creates_private_key_and_csr,
    subtest_update_retrieves_new_cert,
)
from tests.lib.alb.update import subtest_removes_certificate_from_alb
from tests.lib.cdn.update import (
    subtest_update_does_not_remove_old_TXT_records,
)

from tests.lib.cdn.provision import (
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_waits_for_cloudfront_distribution,
    subtest_provision_provisions_ALIAS_records,
)
from tests.integration.cdn_dedicated_waf.provision import (
    subtest_provision_create_web_acl,
    subtest_provision_put_web_acl_logging_configuration,
)
from tests.integration.dedicated_alb.test_dedicated_alb_provisioning import (
    subtest_provision_dedicated_alb_instance,
)


def test_update_dedicated_alb_to_cdn_dedicated_waf_happy_path(
    client,
    dns,
    tasks,
    route53,
    iam_govcloud,
    simple_regex,
    alb,
    organization_guid,
    space_guid,
    clean_db,
    service_instance_id,
    iam_commercial,
    wafv2,
    cloudfront,
):
    subtest_provision_dedicated_alb_instance(
        client,
        dns,
        tasks,
        route53,
        iam_govcloud,
        simple_regex,
        alb,
        organization_guid,
        space_guid,
        service_instance_id=service_instance_id,
    )

    client.update_dedicated_alb_to_cdn_dedicated_waf_instance(
        service_instance_id, params={"alarm_notification_email": "fake@local.host"}
    )
    assert client.response.status_code == 202, client.response.json
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]

    operation = clean_db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == service_instance_id

    clean_db.session.expunge_all()

    check_last_operation_description(
        client, service_instance_id, operation_id, "Queuing tasks"
    )

    instance_model = MigrateDedicatedALBToCDNDedicatedWafServiceInstance

    subtest_update_creates_private_key_and_csr(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client,
        service_instance_id,
        operation_id,
        "Creating credentials for Lets Encrypt",
    )
    subtest_provision_initiates_LE_challenge(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Initiating Lets Encrypt challenges"
    )
    subtest_provision_updates_TXT_records(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Updating DNS TXT records"
    )
    subtest_provision_waits_for_route53_changes(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Waiting for DNS changes"
    )
    subtest_update_does_not_remove_old_TXT_records(tasks, route53)
    subtest_provision_answers_challenges(
        tasks, dns, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Answering Lets Encrypt challenges"
    )
    subtest_update_retrieves_new_cert(
        tasks, instance_model, service_instance_id=service_instance_id
    )
    subtest_provision_uploads_certificate_to_iam(
        tasks,
        iam_commercial,
        simple_regex,
        instance_model,
        service_instance_id=service_instance_id,
    )
    subtest_provision_create_web_acl(
        tasks, wafv2, instance_model, service_instance_id=service_instance_id
    )
    subtest_provision_put_web_acl_logging_configuration(
        tasks, wafv2, instance_model, service_instance_id=service_instance_id
    )
    subtest_migrate_creates_cloudfront_distribution(
        tasks, cloudfront, instance_model, service_instance_id=service_instance_id
    )
    subtest_provision_waits_for_cloudfront_distribution(
        tasks, cloudfront, instance_model, service_instance_id=service_instance_id
    )
    subtest_provision_provisions_ALIAS_records(
        tasks, route53, instance_model, service_instance_id=service_instance_id
    )

    # instance = clean_db.session.get(DedicatedALBServiceInstance, service_instance_id)
    # assert instance.instance_type == ServiceInstanceTypes.DEDICATED_ALB.value

    # subtest_removes_certificate_from_alb(
    #     tasks, alb, instance_model, service_instance_id=service_instance_id
    # )
    # subtest_is_cdn_dedicated_waf_instance(service_instance_id=service_instance_id)


def subtest_migrate_creates_cloudfront_distribution(
    tasks, cloudfront, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    certificate = service_instance.new_certificate

    id_ = certificate.id

    dedicated_waf_web_acl_arn = service_instance.dedicated_waf_web_acl_arn

    cloudfront.expect_create_distribution_with_tags(
        caller_reference=service_instance.id,
        domains=service_instance.domain_names,
        certificate_id=certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id="FakeDistributionId",
        distribution_hostname="fake1234.cloudfront.net",
        bucket_prefix=f"{service_instance_id}/",
        dedicated_waf_web_acl_arn=dedicated_waf_web_acl_arn,
        tags=service_instance.tags,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    assert service_instance.cloudfront_distribution_arn
    assert service_instance.cloudfront_distribution_arn.startswith("arn:aws:cloudfront")
    assert service_instance.cloudfront_distribution_arn.endswith("FakeDistributionId")
    assert service_instance.cloudfront_distribution_id == "FakeDistributionId"
    assert service_instance.domain_internal == "fake1234.cloudfront.net"
    assert service_instance.new_certificate is None
    assert service_instance.current_certificate is not None
    assert service_instance.current_certificate.id == id_
    assert service_instance.tags is not None
