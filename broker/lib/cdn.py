from broker.models import ServiceInstanceTypes


def is_cdn_instance(service_instance):
    return service_instance.instance_type in [
        ServiceInstanceTypes.CDN.value,
        ServiceInstanceTypes.CDN_DEDICATED_WAF.value,
    ]
