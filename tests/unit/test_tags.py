import random
import pytest
import uuid
import json

from openbrokerapi.service_broker import (
    ProvisionDetails,
    ServicePlan,
    Service,
)

from broker.lib.tags import (
    add_tag,
    create_resource_tags,
    generate_tags,
    generate_instance_tags,
)
from tests.lib.tags import sort_instance_tags


@pytest.fixture
def instance_guid():
    return str(uuid.uuid4())


@pytest.fixture
def plan_id():
    return str(uuid.uuid4())


@pytest.fixture
def plan_name():
    return f"plan-{random.choice(range(1000))}"


@pytest.fixture
def plan(plan_id, plan_name):
    return ServicePlan(plan_id, plan_name, "plan description")


@pytest.fixture
def details(plan, organization_guid, space_guid):
    return ProvisionDetails(
        uuid.uuid4(),
        plan.id,
        organization_guid=organization_guid,
        space_guid=space_guid,
    )


@pytest.fixture
def catalog(plan):
    return Service(
        uuid.uuid4(), "external-domain", "external domain plans", False, plans=[plan]
    )


def test_add_tag():
    tags = add_tag([], {"Key": "foo", "Value": "bar"})
    assert tags == [{"Key": "foo", "Value": "bar"}]


def test_add_tag_errors_on_existing_tag():
    tags = [{"Key": "foo", "Value": "bar"}]
    with pytest.raises(RuntimeError):
        add_tag(tags, {"Key": "foo", "Value": "bar"})


def test_generate_instance_tags(
    instance_guid,
    organization_guid,
    space_guid,
    plan,
    details,
    catalog,
    access_token,
    mock_with_uaa_auth,
):
    response = json.dumps({"guid": organization_guid, "name": "org-1234"})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/organizations/{organization_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )
    response = json.dumps({"guid": space_guid, "name": "space-5678"})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/spaces/{space_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    tags = generate_instance_tags(instance_guid, details, catalog, "foo")
    assert sort_instance_tags(tags) == sort_instance_tags(
        [
            {"Key": "client", "Value": "Cloud Foundry"},
            {"Key": "broker", "Value": "External domain broker"},
            {"Key": "environment", "Value": "foo"},
            {"Key": "Service offering name", "Value": "external-domain"},
            {"Key": "Service plan name", "Value": plan.name},
            {"Key": "Instance GUID", "Value": instance_guid},
            {"Key": "Organization GUID", "Value": organization_guid},
            {"Key": "Organization name", "Value": "org-1234"},
            {"Key": "Space GUID", "Value": space_guid},
            {"Key": "Space name", "Value": "space-5678"},
        ]
    )


def test_generate_instance_tags_multiple_plans(instance_guid, plan, details, catalog):
    catalog.plans = [plan, plan]
    with pytest.raises(RuntimeError):
        generate_instance_tags(instance_guid, details, catalog, "foo")


def test_generate_instance_tags_no_matching_plans(
    instance_guid, plan, details, catalog
):
    plan.id = str(uuid.uuid4())
    catalog.plans = [plan]
    with pytest.raises(RuntimeError):
        generate_instance_tags(instance_guid, details, catalog, "foo")


def test_create_resource_tags():
    tags = {"foo": "bar", "moo": "cow"}
    assert create_resource_tags(tags) == [
        {"Key": "foo", "Value": "bar"},
        {"Key": "moo", "Value": "cow"},
    ]


def test_generate_tags(
    instance_guid,
    organization_guid,
    space_guid,
    plan,
    details,
    access_token,
    mock_with_uaa_auth,
):
    response = json.dumps({"guid": organization_guid, "name": "org-1234"})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/organizations/{organization_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )
    response = json.dumps({"guid": space_guid, "name": "space-5678"})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/spaces/{space_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert generate_tags(
        "foo",
        instance_guid=instance_guid,
        offering_name="offering-1",
        plan_name=plan.name,
        space_guid=details.space_guid,
        organization_guid=details.organization_guid,
    ) == {
        "client": "Cloud Foundry",
        "broker": "External domain broker",
        "environment": "foo",
        "Service offering name": "offering-1",
        "Service plan name": plan.name,
        "Instance GUID": instance_guid,
        "Organization GUID": organization_guid,
        "Organization name": "org-1234",
        "Space GUID": space_guid,
        "Space name": "space-5678",
    }


def test_generate_tags_subset(
    organization_guid,
    details,
    access_token,
    mock_with_uaa_auth,
):
    response = json.dumps({"guid": organization_guid, "name": "org-1234"})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/organizations/{organization_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert generate_tags(
        "foo",
        organization_guid=details.organization_guid,
    ) == {
        "client": "Cloud Foundry",
        "broker": "External domain broker",
        "environment": "foo",
        "Organization GUID": organization_guid,
        "Organization name": "org-1234",
    }
