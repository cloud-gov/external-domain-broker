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


def subtest_update_noop(client):
    client.update_alb_instance("4321", params={"domains": "bar.com, Foo.com"})
    assert client.response.status_code == 200
