import typing

from broker.extensions import config

from openbrokerapi.service_broker import (
    ProvisionDetails,
)


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


def generate_default_tags(
    instance_id: str, details: ProvisionDetails
) -> typing.Dict[str, str]:
    default_tags = {
        "client": "Cloud Foundry",
        "broker": "External domain broker",
        "environment": config.FLASK_ENV,
        "Instance GUID": instance_id,
        "Organization GUID": details.organization_guid,
        "Space GUID": details.space_guid,
    }
    return default_tags
