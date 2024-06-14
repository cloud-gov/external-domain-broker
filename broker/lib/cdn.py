def is_cdn_instance(service_instance):
    return service_instance.instance_type in [
        "cdn_service_instance",
        "cdn_dedicated_waf_service_instance",
    ]


def add_cdn_tag(tags, tag_key: str, tag_value: str):
    tags["Items"] = tags["Items"] if "Items" in tags else []
    tags["Items"].append(
        {
            "Key": tag_key,
            "Value": tag_value,
        }
    )
    return tags
