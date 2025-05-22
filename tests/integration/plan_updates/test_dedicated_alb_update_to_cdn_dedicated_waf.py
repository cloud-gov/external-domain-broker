from broker.models import (
    DedicatedALBServiceInstance,
    CDNDedicatedWAFServiceInstance,
    MigrateDedicatedALBToCDNDedicatedWafServiceInstance,
    Operation,
    ServiceInstanceTypes,
)

from tests.lib.client import check_last_operation_description

from tests.lib.provision import (
    subtest_provision_creates_private_key_and_csr,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_answers_challenges,
)
from tests.lib.alb.update import subtest_removes_certificate_from_alb
from tests.lib.cdn.update import (
    subtest_update_does_not_create_new_TXT_records,
    subtest_update_does_not_remove_old_TXT_records,
)

from tests.lib.cdn.provision import (
    subtest_provision_retrieves_certificate,
    subtest_provision_uploads_certificate_to_iam,
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
        service_instance_id,
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

    subtest_provision_creates_private_key_and_csr(
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
    subtest_update_does_not_create_new_TXT_records(
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
    subtest_provision_retrieves_certificate(
        tasks, instance_model, service_instance_id=service_instance_id
    )

    subtest_provision_uploads_certificate_to_iam(
        tasks,
        iam_commercial,
        simple_regex,
        instance_model,
        service_instance_id=service_instance_id,
    )

    # instance = clean_db.session.get(DedicatedALBServiceInstance, service_instance_id)
    # assert instance.instance_type == ServiceInstanceTypes.DEDICATED_ALB.value

    # subtest_removes_certificate_from_alb(
    #     tasks, alb, instance_model, service_instance_id=service_instance_id
    # )
    # subtest_is_cdn_dedicated_waf_instance(service_instance_id=service_instance_id)
