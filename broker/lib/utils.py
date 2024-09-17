import logging

from broker import validators
from broker.models import (
    ServiceInstanceTypes,
    CDNServiceInstance,
)

logger = logging.getLogger(__name__)


def parse_cookie_options(params):
    forward_cookies = params.get("forward_cookies", None)
    if forward_cookies is not None:
        forward_cookies = forward_cookies.replace(" ", "")
        if forward_cookies == "":
            forward_cookie_policy = CDNServiceInstance.ForwardCookiePolicy.NONE.value
            forwarded_cookies = []
        elif forward_cookies == "*":
            forward_cookie_policy = CDNServiceInstance.ForwardCookiePolicy.ALL.value
            forwarded_cookies = []
        else:
            forward_cookie_policy = (
                CDNServiceInstance.ForwardCookiePolicy.WHITELIST.value
            )
            forwarded_cookies = forward_cookies.split(",")
    else:
        forward_cookie_policy = CDNServiceInstance.ForwardCookiePolicy.ALL.value
        forwarded_cookies = []

    return forward_cookie_policy, forwarded_cookies


def parse_header_options(params):
    forwarded_headers = params.get("forward_headers", None)
    if forwarded_headers is None:
        forwarded_headers = []
    else:
        forwarded_headers = forwarded_headers.replace(" ", "")
        forwarded_headers = forwarded_headers.split(",")
    validators.HeaderList(forwarded_headers).validate()
    return forwarded_headers


def normalize_header_list(headers):
    headers = {header.upper() for header in headers}
    return sorted(list(headers))


def parse_domain_options(params) -> list[str]:
    domains = params.get("domains", [])
    if isinstance(domains, str):
        domains = domains.split(",")
    if isinstance(domains, list):
        return [d.strip().lower() for d in domains]


def parse_alarm_notification_email(instance, params):
    alarm_notification_email = None
    if (
        "alarm_notification_email" in params
        and instance.instance_type == ServiceInstanceTypes.CDN_DEDICATED_WAF.value
    ):
        alarm_notification_email = params["alarm_notification_email"]
    return alarm_notification_email


def validate_domain_name_changes(requested_domain_names, instance) -> list[str]:
    if len(requested_domain_names) > 0:
        logger.info("validating CNAMEs")
        validators.CNAME(requested_domain_names).validate()

        logger.info("validating unique domains")
        validators.UniqueDomains(requested_domain_names).validate(instance)

        if sorted(requested_domain_names) == sorted(instance.domain_names):
            return []

    return requested_domain_names
