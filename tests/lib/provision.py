import json

import pytest  # noqa F401

from broker.extensions import db
from broker.models import (
    Challenge,
)


def subtest_provision_creates_LE_user(tasks, instance_model):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(instance_model, "4321")
    acme_user = service_instance.acme_user
    assert acme_user
    assert "RSA" in acme_user.private_key_pem
    assert "@gsa.gov" in acme_user.email
    assert "localhost:14000" in acme_user.uri
    assert "body" in json.loads(acme_user.registration_json)


def subtest_provision_creates_private_key_and_csr(tasks, instance_model):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(instance_model, "4321")
    assert len(service_instance.certificates) == 1

    assert "BEGIN PRIVATE KEY" in service_instance.new_certificate.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in service_instance.new_certificate.csr_pem


def subtest_provision_initiates_LE_challenge(tasks, instance_model):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(instance_model, "4321")

    assert service_instance.new_certificate.challenges.count() == 2
    assert service_instance.new_certificate.order_json is not None


def subtest_provision_updates_TXT_records(tasks, route53, instance_model):
    example_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.example.com.domains.cloud.test"
    )
    foo_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.foo.com.domains.cloud.test"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.route53_change_ids == [
        example_com_change_id,
        foo_com_change_id,
    ]


def subtest_provision_waits_for_route53_changes(tasks, route53, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_provision_answers_challenges(tasks, dns, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate

    example_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%example.com")
    ).first()

    foo_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%foo.com")
    ).first()

    dns.add_txt(
        "_acme-challenge.example.com.domains.cloud.test.",
        example_com_challenge.validation_contents,
    )

    dns.add_txt(
        "_acme-challenge.foo.com.domains.cloud.test.",
        foo_com_challenge.validation_contents,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate
    answered = [c.answered for c in certificate.challenges]
    assert answered == [True, True]


def subtest_provision_marks_operation_as_succeeded(tasks, instance_model):
    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state
