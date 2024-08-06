from datetime import date

import pytest  # noqa F401

from broker.extensions import db
from broker.models import Challenge, Operation


def subtest_update_creates_private_key_and_csr(tasks, instance_model):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate
    assert "BEGIN PRIVATE KEY" in certificate.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in certificate.csr_pem
    assert len(service_instance.certificates) == 2
    assert service_instance.current_certificate is not None
    assert service_instance.new_certificate is not None
    assert (
        service_instance.current_certificate.id != service_instance.new_certificate.id
    )


def subtest_gets_new_challenges(tasks, instance_model):
    db.session.expunge_all()
    tasks.run_queued_tasks_and_enqueue_dependents()

    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate

    assert len(certificate.challenges.all()) == 2
    assert sorted(certificate.subject_alternative_names) == sorted(
        ["bar.com", "foo.com"]
    )


def subtest_update_updates_TXT_records(tasks, route53, instance_model):
    bar_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.bar.com.domains.cloud.test"
    )
    foo_com_change_id = route53.expect_create_TXT_and_return_change_id(
        "_acme-challenge.foo.com.domains.cloud.test"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.route53_change_ids == [bar_com_change_id, foo_com_change_id]


def subtest_update_answers_challenges(tasks, dns, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate

    bar_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%bar.com"), Challenge.answered.is_(False)
    ).first()

    foo_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%foo.com"), Challenge.answered.is_(False)
    ).first()

    dns.add_txt(
        "_acme-challenge.bar.com.domains.cloud.test.",
        bar_com_challenge.validation_contents,
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


def subtest_waits_for_dns_changes(
    tasks, route53, instance_model, service_instance_id="4321"
):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)

    for change_id in service_instance.route53_change_ids:
        route53.expect_wait_for_change_insync(change_id)

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    assert service_instance.route53_change_ids == []
    route53.assert_no_pending_responses()


def subtest_update_retrieves_new_cert(tasks, instance_model):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None


def subtest_update_marks_update_complete(
    tasks, instance_model, service_instance_id="4321"
):
    tasks.run_queued_tasks_and_enqueue_dependents()
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, service_instance_id)
    operation = service_instance.operations.first()
    assert operation
    assert "succeeded" == operation.state


def subtest_update_removes_certificate_from_iam(tasks, iam, instance_model):
    iam.expects_delete_server_certificate(f"4321-{date.today().isoformat()}-1")

    tasks.run_queued_tasks_and_enqueue_dependents()

    iam.assert_no_pending_responses()
    instance = db.session.get(instance_model, "4321")
    assert len(instance.certificates) == 1


def subtest_update_same_domains_creates_update_operation(client, dns, instance_model):
    dns.add_cname("_acme-challenge.foo.com")
    dns.add_cname("_acme-challenge.bar.com")
    client.update_instance(
        instance_model,
        "4321",
        params={
            "domains": "bar.com, Foo.com",
            "origin": "newer-origin.com",
            "error_responses": {},
        },
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Update"
    assert operation.service_instance_id == "4321"

    instance = db.session.get(instance_model, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["bar.com", "foo.com"]
    assert instance.cloudfront_origin_hostname == "newer-origin.com"
    return operation_id


def subtest_update_same_domains_does_not_create_new_certificate(tasks, instance_model):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(instance_model, "4321")
    assert len(instance.certificates) == 1


def subtest_update_same_domains_does_not_create_new_challenges(tasks, instance_model):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(instance_model, "4321")
    certificate = instance.new_certificate
    assert len(certificate.challenges.all()) == 2
    assert all([c.answered for c in certificate.challenges])


def subtest_update_same_domains_does_not_update_route53(tasks, route53, instance_model):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(instance_model, "4321")
    assert not instance.route53_change_ids
    route53.assert_no_pending_responses()
    # should run wait for changes, which should do nothing
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_update_same_domains_does_not_retrieve_new_certificate(tasks):
    # the idea here is that we don't have new challenges, so asking
    # for a new certificate should raise an error.
    # no errors = did not try to ask for a new certificate
    tasks.run_queued_tasks_and_enqueue_dependents()  # answer_challenges
    tasks.run_queued_tasks_and_enqueue_dependents()  # retrieve_certificate


def subtest_update_same_domains_does_not_update_iam(tasks):
    # if we don't prime IAM to expect a call, then we didn't update iam
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_update_same_domains_does_not_delete_server_certificate(
    tasks, instance_model
):
    tasks.run_queued_tasks_and_enqueue_dependents()
    instance = db.session.get(instance_model, "4321")
    assert len(instance.certificates) == 1


def subtest_update_updates_ALIAS_records(tasks, route53, instance_model):
    bar_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "bar.com.domains.cloud.test", "fake1234.cloudfront.net"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "fake1234.cloudfront.net"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    route53.assert_no_pending_responses()
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    assert service_instance.route53_change_ids == [bar_com_change_id, foo_com_change_id]
