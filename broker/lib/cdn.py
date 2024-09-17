from broker.models import ServiceInstanceTypes


def is_cdn_instance(service_instance) -> bool:
    return service_instance.instance_type in [
        ServiceInstanceTypes.CDN.value,
        ServiceInstanceTypes.CDN_DEDICATED_WAF.value,
    ]


def is_cdn_dedicated_waf_instance(service_instance) -> bool:
    return (
        service_instance.instance_type == ServiceInstanceTypes.CDN_DEDICATED_WAF.value
    )
