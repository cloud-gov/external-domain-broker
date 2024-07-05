import random
import pytest
import uuid

from openbrokerapi.service_broker import (
    ProvisionDetails,
    ServicePlan,
    Service,
)

from broker.lib.tags import create_resource_tags, generate_tags, generate_instance_tags


@pytest.fixture
def instance_id():
    return str(uuid.uuid4())


@pytest.fixture
def plan_id():
    return str(uuid.uuid4())


@pytest.fixture
def plan_name():
    return f"plan-{random.choice(range(1000))}"


@pytest.fixture
def org_guid():
    return str(uuid.uuid4())


@pytest.fixture
def space_guid():
    return str(uuid.uuid4())


@pytest.fixture
def plan(plan_id, plan_name):
    return ServicePlan(plan_id, plan_name, "plan description")


@pytest.fixture
def details(plan, org_guid, space_guid):
    return ProvisionDetails(
        uuid.uuid4(), plan.id, organization_guid=org_guid, space_guid=space_guid
    )


def test_generate_instance_tags():
    instance_id = str(uuid.uuid4())
    plan = ServicePlan(uuid.uuid4(), "plan-1", "plan description")
    catalog = Service(
        uuid.uuid4(), "external-domain", "external domain plans", plans=[plan]
    )
    details = ProvisionDetails(
        uuid.uuid4(), plan.id, organization_guid="org-1", space_guid="space-1"
    )

    tags = generate_instance_tags(instance_id, details, catalog)
    assert tags == {
        "Items": [
            {"Key": "client", "Value": "Cloud Foundry"},
            {"Key": "broker", "Value": "External domain broker"},
            {"Key": "environment", "Value": "test"},
            {"Key": "Service offering name", "Value": "external-domain"},
            {"Key": "Service plan name", "Value": "plan-1"},
        ]
    }


def test_create_resource_tags():
    tags = {"foo": "bar", "moo": "cow"}
    assert create_resource_tags(tags) == {
        "Items": [{"Key": "foo", "Value": "bar"}, {"Key": "moo", "Value": "cow"}]
    }


def test_generate_tags(instance_id, org_guid, space_guid, plan, details):
    assert generate_tags(
        instance_id,
        "offering-1",
        plan,
        details,
    ) == {
        "client": "Cloud Foundry",
        "broker": "External domain broker",
        "environment": "test",
        "Service offering name": "offering-1",
        "Service plan name": plan.name,
        "Instance GUID": instance_id,
        "Organization GUID": org_guid,
        "Space GUID": space_guid,
    }
