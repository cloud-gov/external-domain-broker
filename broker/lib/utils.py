import logging

from broker import validators
from broker.extensions import db
from broker.lib.cdn import is_cdn_instance
from broker.models import (
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


def parse_domain_options(params):
    domains = params.get("domains", None)
    if isinstance(domains, str):
        domains = domains.split(",")
    if isinstance(domains, list):
        return [d.strip().lower() for d in domains]


def handle_domain_updates(params, instance):
    domain_names = parse_domain_options(params)
    no_domain_updates = True
    if domain_names is not None:
        logger.info("validating CNAMEs")
        validators.CNAME(domain_names).validate()

        logger.info("validating unique domains")
        validators.UniqueDomains(domain_names).validate(instance)
        # If domain names have not changed, then there is no need for a new certificate
        no_domain_updates = no_domain_updates and (
            sorted(domain_names) == sorted(instance.domain_names)
        )
        instance.domain_names = domain_names

    if is_cdn_instance(instance) and no_domain_updates:
        logger.info("domains unchanged, no need for new certificate")
        instance.new_certificate = instance.current_certificate

    return (instance, no_domain_updates)
