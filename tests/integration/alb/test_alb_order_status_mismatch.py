"""
This is about testing an issue where our order goes from ready to valid when we're not looking.
I _think_ this can be any of these:
- timing issue
- issue on Let's Encrypt (e.g. timeout error)
- our app crashes/errors/is stopped after finalizing but before persisting certificate
It doesn't matter that this test is on ALB - the same issue occurs for the same reason on either
instance type, but there's no need to test both cases.
"""

import pytest
from broker.extensions import config, db
from broker.models import ALBServiceInstance
from broker.tasks.letsencrypt import retrieve_certificate

from tests.lib.provision import (
    subtest_provision_creates_LE_user,
    subtest_provision_creates_private_key_and_csr,
    subtest_provision_initiates_LE_challenge,
    subtest_provision_updates_TXT_records,
    subtest_provision_waits_for_route53_changes,
    subtest_provision_answers_challenges,
)
from tests.lib.alb.provision import (
    subtest_provision_creates_provision_operation,
    subtest_provision_retrieves_certificate,
)


def test_stuff(client, dns, tasks, route53):
    # get us into the right state
    instance_model = ALBServiceInstance
    task_id = subtest_provision_creates_provision_operation(client, dns, instance_model)
    subtest_provision_creates_LE_user(tasks, instance_model)
    subtest_provision_creates_private_key_and_csr(tasks, instance_model)
    subtest_provision_initiates_LE_challenge(tasks, instance_model)
    subtest_provision_updates_TXT_records(tasks, route53, instance_model)
    subtest_provision_waits_for_route53_changes(tasks, route53, instance_model)
    subtest_provision_answers_challenges(tasks, dns, instance_model)
    subtest_provision_retrieves_certificate(tasks, instance_model)
    # at this point, the order should be valid.
    # modify the service instance to sidestep idempotency checks
    instance = db.session.get(ALBServiceInstance, "4321")
    instance.new_certificate.leaf_pem = None
    instance.new_certificate.fullchain_pem = None
    instance.new_certificate.expires_at = None
    operation_id = instance.operations[0].id
    db.session.commit()
    db.session.expunge_all()

    # now, try to retrieve the certificate again.
    # if this bug is present, this should raise an exception.
    retrieve_certificate.call_local(operation_id)
