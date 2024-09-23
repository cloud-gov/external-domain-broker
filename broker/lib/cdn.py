from broker.models import (
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
)


def is_cdn_instance(service_instance) -> bool:
    return isinstance(service_instance, CDNServiceInstance) or isinstance(
        service_instance, CDNDedicatedWAFServiceInstance
    )


def is_cdn_dedicated_waf_instance(service_instance) -> bool:
    return isinstance(service_instance, CDNDedicatedWAFServiceInstance)
