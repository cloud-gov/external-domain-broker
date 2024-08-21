from datetime import date
import json
import pytest  # noqa F401

from broker.extensions import db
from broker.models import (
    Operation,
    ALBServiceInstance,
    DedicatedALBServiceInstance,
)


def subtest_provision_uploads_certificate_to_iam(
    tasks, iam_govcloud, simple_regex, instance_model
):
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
    tags = service_instance.tags if service_instance.tags else []
    iam_govcloud.expect_tag_server_certificate(
        f"{service_instance.id}-{today}-{certificate.id}",
        tags,
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


def subtest_provision_creates_provision_operation(
    client, dns, organization_guid, space_guid, instance_model
):
    dns.add_cname("_acme-challenge.example.com")
    dns.add_cname("_acme-challenge.foo.com")
    client.provision_instance(
        instance_model,
        "4321",
        params={"domains": "example.com, Foo.com"},
        organization_guid=organization_guid,
        space_guid=space_guid,
    )
    db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == "in progress"
    assert operation.action == "Provision"
    assert operation.service_instance_id == "4321"

    instance = db.session.get(instance_model, operation.service_instance_id)
    assert instance is not None
    assert instance.domain_names == ["example.com", "foo.com"]

    if instance_model == ALBServiceInstance:
        service_plan_name = "domain"
    elif instance_model == DedicatedALBServiceInstance:
        service_plan_name = "domain-with-org-lb"
    assert instance.tags == [
        {"Key": "client", "Value": "Cloud Foundry"},
        {"Key": "broker", "Value": "External domain broker"},
        {"Key": "environment", "Value": "test"},
        {"Key": "Service offering name", "Value": "external-domain"},
        {"Key": "Service plan name", "Value": service_plan_name},
        {"Key": "Instance GUID", "Value": "4321"},
        {"Key": "Organization GUID", "Value": organization_guid},
        {"Key": "Space GUID", "Value": space_guid},
    ]

    return operation_id


def subtest_provision_provisions_ALIAS_records(tasks, route53, instance_model):
    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    example_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "example.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    foo_com_change_id = route53.expect_create_ALIAS_and_return_change_id(
        "foo.com.domains.cloud.test", "alb.cloud.test", "ALBHOSTEDZONEID"
    )
    tasks.run_queued_tasks_and_enqueue_dependents()


def subtest_provision_retrieves_certificate(tasks, instance_model):
    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(instance_model, "4321")
    certificate = service_instance.new_certificate

    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires_at is not None
    assert json.loads(certificate.order_json)["body"]["status"] == "valid"
