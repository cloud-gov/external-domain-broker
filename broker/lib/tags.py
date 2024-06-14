def add_tag(tags, tag_key: str, tag_value: str):
    if not tags:
        tags = {}
    tags["Items"] = tags["Items"] if "Items" in tags else []
    tags["Items"].append(
        {
            "Key": tag_key,
            "Value": tag_value,
        }
    )
    return tags
