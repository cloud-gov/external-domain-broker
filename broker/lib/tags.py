import typing

from broker.extensions import config

from enum import Enum
from openbrokerapi.service_broker import (
    ProvisionDetails,
    ServicePlan,
    Service,
)


class Action(Enum):
    CREATE = "Create"
    UPDATE = "Update"


def add_tag(tags, tag_key: str, tag_value: str):
    if not tags:
        tags = {}
    tags["Items"] = tags.get("Items", [])
    tags["Items"].append(
        {
            "Key": tag_key,
            "Value": tag_value,
        }
    )
    return tags


def generate_instance_tags(
    instance_id: str, details: ProvisionDetails, catalog: Service
):
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


def create_resource_tags(tags: typing.Dict[str, str]):
    resource_tags = {}
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
        # TODO: add tags for org name, space name
        "Organization GUID": details.organization_guid,
        "Space GUID": details.space_guid,
    }
    return default_tags
