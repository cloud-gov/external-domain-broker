import uuid

from openbrokerapi.service_broker import (
    ProvisionDetails,
    ServicePlan,
)

from broker.lib.tags import generate_default_tags


def test_generate_default_tags():
    instance_id = str(uuid.uuid4())
    plan = ServicePlan(uuid.uuid4(), "plan-1", "plan description")
    details = ProvisionDetails(
        uuid.uuid4(), plan.id, organization_guid="org-1", space_guid="space-1"
    )

    generate_default_tags(
        instance_id,
        "offering-1",
        plan,
        details,
    ) == {
        "client": "Cloud Foundry",
        "broker": "External domain broker",
        "environment": "test",
        "Service offering name": "offering-1",
        "Service plan name": "plan-1",
        "Instance GUID": instance_id,
        "Organization GUID": "org-1",
        "Space GUID": "space-1",
    }
