from datetime import date
from broker.extensions import db


def subtest_update_provisions_ALIAS_records(tasks, route53, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    example_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "bar.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_update_uploads_new_cert(tasks, iam_govcloud, simple_regex, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate
    today = date.today().isoformat()
    assert today == simple_regex(r"^\d\d\d\d-\d\d-\d\d$")

    iam_govcloud.expect_upload_server_certificate(
        name=f"{service_instance.id}-{today}-{certificate.id}",
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path="/alb/external-domains-test/",
    )
    iam_govcloud.expect_tag_server_certificate(
        f"{service_instance.id}-{today}-{certificate.id}",
        service_instance.tags,
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate
    assert certificate.iam_server_certificate_name
    assert certificate.iam_server_certificate_name.startswith("4321")
    assert certificate.iam_server_certificate_id
    assert certificate.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert certificate.iam_server_certificate_arn
    assert certificate.iam_server_certificate_arn.startswith("arn:aws:iam")


def subtest_update_noop(client, instance_model):
    client.update_instance(
        instance_model, "4321", params={"domains": "bar.com, Foo.com"}
    )
    assert client.response.status_code == 200


def subtest_removes_previous_certificate_from_alb(
    tasks, alb, listener_arn, certificate_arn
):
    alb.expect_remove_certificate_from_listener(
        listener_arn,
        certificate_arn,
    )
    alb.expect_get_certificates_for_listener(listener_arn, 0)

    tasks.run_queued_tasks_and_enqueue_dependents()

    alb.assert_no_pending_responses()


def subtest_update_removes_old_DNS_records(
    tasks, route53, instance_model, service_instance_id="4321"
):
    service_instance = db.session.get(instance_model, service_instance_id)
    challenges = service_instance.current_certificate.challenges.all()
    challenge = next(
        (challenge for challenge in challenges if challenge.domain == "example.com"),
        None,
    )

    route53.expect_remove_TXT(
        "_acme-challenge.example.com.domains.cloud.test", challenge.validation_contents
    )
    route53.expect_remove_ALIAS(
        "example.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )

    tasks.run_queued_tasks_and_enqueue_dependents()

    route53.assert_no_pending_responses()
