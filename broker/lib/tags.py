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
