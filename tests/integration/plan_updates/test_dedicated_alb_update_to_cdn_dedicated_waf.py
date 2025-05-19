import pytest

from broker.models import CDNDedicatedWAFServiceInstance, Operation

from tests.lib import factories
from tests.lib.client import check_last_operation_description

from tests.lib.provision import (
    subtest_provision_creates_LE_user,
    subtest_provision_creates_private_key_and_csr,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_answers_challenges,
)

from tests.lib.cdn.provision import (
    subtest_provision_retrieves_certificate,
)

from tests.integration.dedicated_alb.test_dedicated_alb_provisioning import (
    subtest_provision_dedicated_alb_instance,
)

from tests.integration.plan_updates.test_cdn_update_to_cdn_dedicated_waf import (
    subtest_is_cdn_dedicated_waf_instance,
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

    instance = clean_db.session.get(CDNDedicatedWAFServiceInstance, service_instance_id)
    assert instance is not None

    subtest_is_cdn_dedicated_waf_instance(service_instance_id=service_instance_id)
    check_last_operation_description(
        client, service_instance_id, operation_id, "Queuing tasks"
    )
    instance_model = CDNDedicatedWAFServiceInstance

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
    subtest_provision_answers_challenges(
        tasks, dns, instance_model, service_instance_id=service_instance_id
    )
    check_last_operation_description(
        client, service_instance_id, operation_id, "Answering Lets Encrypt challenges"
    )
    subtest_provision_retrieves_certificate(
        tasks, instance_model, service_instance_id=service_instance_id
    )
