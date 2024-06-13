import json
from datetime import date

import pytest  # noqa F401

from broker.extensions import config, db
from broker.models import (
    Challenge,
    Operation,
    DedicatedALBServiceInstance,
    DedicatedALBListener,
)

from tests.lib.client import check_last_operation_description
from tests.lib.provision import (
    subtest_provision_creates_provision_operation,
    subtest_provision_creates_LE_user,
    subtest_provision_creates_private_key_and_csr,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_answers_challenges,
    subtest_provision_retrieves_certificate,
    subtest_provision_uploads_certificate_to_iam,
    subtest_provision_provisions_ALIAS_records,
    subtest_provision_marks_operation_as_succeeded,
)

from tests.integration.dedicated_alb.test_dedicated_alb_update import (
    subtest_update_happy_path,
    subtest_update_noop,
)

# The subtests below are "interesting".  Before test_provision_happy_path, we
# had separate tests for each stage in the task pipeline.  But each test would
# have to duplicate much of the previous test.  This was arduous and slow. Now
# we have a single test_provision_happy_path, and many subtest_foo helper
# methods.  This still makes it clear which stage in the task pipeline is
# failing (look for the subtask_foo in the traceback), and allows us to re-use
# these subtasks when testing failure scenarios.


def test_provision_happy_path(
    client, dns, tasks, route53, iam_govcloud, simple_regex, alb
):
    operation_id = subtest_provision_creates_provision_operation(client, dns)
    check_last_operation_description(client, "4321", operation_id, "Queuing tasks")
    subtest_provision_creates_LE_user(tasks)
    check_last_operation_description(
        client, "4321", operation_id, "Registering user for Lets Encrypt"
    )
    subtest_provision_creates_private_key_and_csr(tasks)
    check_last_operation_description(
        client, "4321", operation_id, "Creating credentials for Lets Encrypt"
    )
    subtest_provision_initiates_LE_challenge(tasks)
    check_last_operation_description(
        client, "4321", operation_id, "Initiating Lets Encrypt challenges"
    )
    subtest_provision_updates_TXT_records(tasks, route53)
    check_last_operation_description(
        client, "4321", operation_id, "Updating DNS TXT records"
    )
    subtest_provision_waits_for_route53_changes(tasks, route53)
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for DNS changes"
    )
    subtest_provision_answers_challenges(tasks, dns)
    check_last_operation_description(
        client, "4321", operation_id, "Answering Lets Encrypt challenges"
    )
    subtest_provision_retrieves_certificate(tasks)
    check_last_operation_description(
        client, "4321", operation_id, "Retrieving SSL certificate from Lets Encrypt"
    )
    subtest_provision_uploads_certificate_to_iam(tasks, iam_govcloud, simple_regex)
    check_last_operation_description(
        client, "4321", operation_id, "Uploading SSL certificate to AWS"
    )
    subtest_provision_selects_dedicated_alb(tasks, alb)
    check_last_operation_description(
        client, "4321", operation_id, "Selecting load balancer"
    )
    subtest_provision_adds_certificate_to_alb(tasks, alb)
    check_last_operation_description(
        client, "4321", operation_id, "Adding SSL certificate to load balancer"
    )
    subtest_provision_provisions_ALIAS_records(tasks, route53, alb)
    check_last_operation_description(
        client, "4321", operation_id, "Creating DNS ALIAS records"
    )
    subtest_provision_waits_for_route53_changes(tasks, route53)
    check_last_operation_description(
        client, "4321", operation_id, "Waiting for DNS changes"
    )
    subtest_provision_marks_operation_as_succeeded(tasks)
    check_last_operation_description(client, "4321", operation_id, "Complete!")
    subtest_update_happy_path(
        client, dns, tasks, route53, iam_govcloud, simple_regex, alb
    )
    subtest_update_noop(client)


def subtest_provision_selects_dedicated_alb(tasks, alb):
    our_listener_0 = DedicatedALBListener(
        listener_arn="our-arn-0", dedicated_org="our-org"
    )
    our_listener_1 = DedicatedALBListener(
        listener_arn="our-arn-1", dedicated_org="our-org"
    )
    empty_listener_0 = DedicatedALBListener(listener_arn="empty-arn-0")
    other_listener_0 = DedicatedALBListener(
        listener_arn="other-arn-0", dedicated_org="other-org"
    )
    other_listener_1 = DedicatedALBListener(
        listener_arn="other-arn-1", dedicated_org="other-org"
    )

    db.session.add_all(
        [
            our_listener_0,
            our_listener_1,
            empty_listener_0,
            other_listener_0,
            other_listener_1,
        ]
    )
    db.session.commit()

    db.session.expunge_all()
    alb.expect_get_certificates_for_listener("our-arn-0", 1)
    alb.expect_get_certificates_for_listener("our-arn-1", 5)
    alb.expect_get_listeners("our-arn-0")
    tasks.run_queued_tasks_and_enqueue_dependents()
    alb.assert_no_pending_responses()
    service_instance = db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.alb_arn.startswith("alb-our-arn-0")


def subtest_provision_adds_certificate_to_alb(tasks, alb):
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
