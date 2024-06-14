def is_cdn_instance(service_instance):
    return service_instance.instance_type in [
        "cdn_service_instance",
        "cdn_dedicated_waf_service_instance",
    ]
