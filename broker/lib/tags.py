import typing

from broker.extensions import config
from broker.lib.cf import CFAPIClient

from enum import Enum
from openbrokerapi.service_broker import (
    ProvisionDetails,
    ServicePlan,
    Service,
)

cf_api_client = CFAPIClient()


class Action(Enum):
    CREATE = "Create"
    UPDATE = "Update"


class Tag(typing.TypedDict):
    Key: str
    Value: str


def add_tag(tags: list[Tag], tag_key: str, tag_value: str) -> list[Tag]:
    if not tags:
        tags = []
    tags.append(
        {
            "Key": tag_key,
            "Value": tag_value,
        }
    )
    return tags


def generate_instance_tags(
    instance_id: str, details: ProvisionDetails, catalog: Service
) -> list[Tag]:
    plans = [plan for plan in catalog.plans if plan.id == details.plan_id]
    if len(plans) == 0:
        raise RuntimeError(
            f"Could not find plan for the given plan ID {details.plan_id}"
        )
    if len(plans) > 1:
        raise RuntimeError(
            f"Found multiple plans for the given plan ID {details.plan_id}"
        )
    return create_resource_tags(
        generate_tags(instance_id, catalog.name, plans[0], details)
    )


def create_resource_tags(tags: typing.Dict[str, str]) -> list[Tag]:
    resource_tags = []
    for tag_key in tags:
        tag_value = tags[tag_key]
        resource_tags = add_tag(resource_tags, tag_key, tag_value)
    return resource_tags


def generate_tags(
    instance_id: str, offering_name: str, plan: ServicePlan, details: ProvisionDetails
) -> typing.Dict[str, str]:
    default_tags = {
        "client": "Cloud Foundry",
        "broker": "External domain broker",
        "environment": config.FLASK_ENV,
        "Service offering name": offering_name,
        "Service plan name": plan.name,
        "Instance GUID": instance_id,
        "Organization GUID": details.organization_guid,
        "Space GUID": details.space_guid,
    }

    space_name = cf_api_client.get_space_name_by_guid(details.space_guid)
    default_tags["Space name"] = space_name

    organization_name = cf_api_client.get_organization_name_by_guid(
        details.organization_guid
    )
    default_tags["Organization name"] = organization_name

    return default_tags
