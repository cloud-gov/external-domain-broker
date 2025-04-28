from openbrokerapi import errors

from broker import validators

from broker.aws import cache_policy_manager
from broker.extensions import config

from broker.lib.cache_policy_manager import CachePolicyManager
from broker.lib.client_error import ClientError
from broker.lib.origin_request_policy_manager import OriginRequestPolicyManager
from broker.lib.utils import (
    parse_cookie_options,
    parse_header_options,
    normalize_header_list,
)
from broker.models import (
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
    Certificate,
    ServiceInstanceTypes,
)


def is_cdn_instance(service_instance) -> bool:
    return isinstance(service_instance, CDNServiceInstance) or isinstance(
        service_instance, CDNDedicatedWAFServiceInstance
    )


def is_cdn_dedicated_waf_instance(service_instance) -> bool:
    return isinstance(service_instance, CDNDedicatedWAFServiceInstance)


def parse_alarm_notification_email(instance, params):
    if not is_cdn_dedicated_waf_instance(instance):
        return None

    return params.get("alarm_notification_email")


def parse_cache_policy(params, cache_policy_manager: CachePolicyManager) -> str:
    cache_policy = params.get("cache_policy", None)
    if not cache_policy:
        return None
    if cache_policy not in config.ALLOWED_AWS_MANAGED_CACHE_POLICIES:
        raise errors.ErrBadRequest(
            f"'{cache_policy}' is not an allowed value for cache_policy."
        )
    return cache_policy_manager.get_managed_policy_id(cache_policy)


def parse_origin_request_policy(
    params, origin_request_policy_manager: OriginRequestPolicyManager
) -> str:
    origin_request_policy = params.get("origin_request_policy", None)
    if not origin_request_policy:
        return None
    if (
        origin_request_policy
        not in config.ALLOWED_AWS_MANAGED_ORIGIN_VIEWER_REQUEST_POLICIES
    ):
        raise errors.ErrBadRequest(
            f"'{origin_request_policy}' is not an allowed value for origin_request_policy."
        )
    return origin_request_policy_manager.get_managed_policy_id(origin_request_policy)


def provision_cdn_instance(
    instance_id: str,
    domain_names: list,
    params: dict,
    instance_type_model: (
        CDNServiceInstance | CDNDedicatedWAFServiceInstance
    ) = CDNServiceInstance,
):
    instance = instance_type_model(id=instance_id, domain_names=domain_names)
    instance.cloudfront_origin_hostname = params.get(
        "origin", config.DEFAULT_CLOUDFRONT_ORIGIN
    )
    validators.Hostname(instance.cloudfront_origin_hostname).validate()
    instance.cloudfront_origin_path = params.get("path", "")
    instance.route53_alias_hosted_zone = config.CLOUDFRONT_HOSTED_ZONE_ID
    forward_cookie_policy, forwarded_cookies = parse_cookie_options(params)
    instance.forward_cookie_policy = forward_cookie_policy
    instance.forwarded_cookies = forwarded_cookies
    forwarded_headers = parse_header_options(params)
    if instance.cloudfront_origin_hostname == config.DEFAULT_CLOUDFRONT_ORIGIN:
        forwarded_headers.append("HOST")
    forwarded_headers = normalize_header_list(forwarded_headers)

    instance.forwarded_headers = forwarded_headers
    instance.error_responses = params.get("error_responses", {})
    validators.ErrorResponseConfig(instance.error_responses).validate()
    if params.get("insecure_origin", False):
        if params.get("origin") is None:
            raise errors.ErrBadRequest(
                "'insecure_origin' cannot be set when using the default origin."
            )
        instance.origin_protocol_policy = instance_type_model.ProtocolPolicy.HTTP.value
    else:
        instance.origin_protocol_policy = instance_type_model.ProtocolPolicy.HTTPS.value

    alarm_notification_email = parse_alarm_notification_email(instance, params)
    if alarm_notification_email:
        instance.alarm_notification_email = alarm_notification_email
    elif is_cdn_dedicated_waf_instance(instance) and not alarm_notification_email:
        raise errors.ErrBadRequest(
            f"'alarm_notification_email' is required for {ServiceInstanceTypes.CDN_DEDICATED_WAF.value} instances"
        )

    cache_policy_id = parse_cache_policy(params, cache_policy_manager)
    if cache_policy_id:
        instance.cache_policy_id = cache_policy_id

    return instance


def update_cdn_instance(params, instance):
    # N.B. we're using "param" in params rather than
    # params.get("param") because the OSBAPI spec
    # requires we do not mess with params that were not
    # specified, so unset and set to None have different meanings
    if "origin" in params:
        if params["origin"]:
            origin_hostname = params["origin"]
            validators.Hostname(origin_hostname).validate()
        else:
            origin_hostname = config.DEFAULT_CLOUDFRONT_ORIGIN
        instance.cloudfront_origin_hostname = origin_hostname

    if "path" in params:
        if params["path"]:
            cloudfront_origin_path = params["path"]
        else:
            cloudfront_origin_path = ""
        instance.cloudfront_origin_path = cloudfront_origin_path
    if "forward_cookies" in params:
        forward_cookie_policy, forwarded_cookies = parse_cookie_options(params)
        instance.forward_cookie_policy = forward_cookie_policy
        instance.forwarded_cookies = forwarded_cookies

    if "forward_headers" in params:
        forwarded_headers = parse_header_options(params)
    else:
        # .copy() so sqlalchemy recognizes the field has changed
        forwarded_headers = instance.forwarded_headers.copy()
    if instance.cloudfront_origin_hostname == config.DEFAULT_CLOUDFRONT_ORIGIN:
        forwarded_headers.append("HOST")
    forwarded_headers = normalize_header_list(forwarded_headers)
    instance.forwarded_headers = forwarded_headers
    if "insecure_origin" in params:
        origin_protocol_policy = "https-only"
        if params["insecure_origin"]:
            if instance.cloudfront_origin_hostname == config.DEFAULT_CLOUDFRONT_ORIGIN:
                raise errors.ErrBadRequest(
                    "Cannot use insecure_origin with default origin"
                )
            origin_protocol_policy = "http-only"
        instance.origin_protocol_policy = origin_protocol_policy
    if "error_responses" in params:
        instance.error_responses = params["error_responses"]
        validators.ErrorResponseConfig(instance.error_responses).validate()

    alarm_notification_email = parse_alarm_notification_email(instance, params)
    if alarm_notification_email:
        instance.alarm_notification_email = alarm_notification_email
    elif (
        is_cdn_dedicated_waf_instance(instance)
        and not instance.alarm_notification_email
    ):
        raise errors.ErrBadRequest(
            f"'alarm_notification_email' is required for {ServiceInstanceTypes.CDN_DEDICATED_WAF.value}"
        )

    cache_policy_id = parse_cache_policy(params, cache_policy_manager)
    if cache_policy_id:
        instance.cache_policy_id = cache_policy_id

    return instance


def validate_migration_to_cdn_params(params):
    required = [
        "origin",
        "path",
        "forwarded_cookies",
        "forward_cookie_policy",
        "forwarded_headers",
        "insecure_origin",
        "error_responses",
        "cloudfront_distribution_id",
        "cloudfront_distribution_arn",
        "iam_server_certificate_name",
        "iam_server_certificate_id",
        "iam_server_certificate_arn",
        "domain_internal",
    ]
    for param in required:
        # since this should only be hit by another app, it seems
        # fair and smart to require all params
        if param not in params:
            raise ClientError(f"Missing parameter {param}")


def update_cdn_params_for_migration(instance, params):
    instance.cloudfront_origin_hostname = params["origin"]
    instance.cloudfront_origin_path = params["path"]
    instance.forwarded_cookies = params["forwarded_cookies"]
    instance.forward_cookie_policy = params["forward_cookie_policy"]
    instance.route53_alias_hosted_zone = config.CLOUDFRONT_HOSTED_ZONE_ID
    if params["insecure_origin"]:
        instance.origin_protocol_policy = CDNServiceInstance.ProtocolPolicy.HTTP.value
    else:
        instance.origin_protocol_policy = CDNServiceInstance.ProtocolPolicy.HTTPS.value
    instance.forwarded_headers = params["forwarded_headers"]
    instance.error_responses = params["error_responses"]
    instance.cloudfront_distribution_id = params["cloudfront_distribution_id"]
    instance.cloudfront_distribution_arn = params["cloudfront_distribution_arn"]
    instance.domain_internal = params["domain_internal"]
    instance.current_certificate = Certificate(service_instance_id=instance.id)
    instance.current_certificate.iam_server_certificate_id = params[
        "iam_server_certificate_id"
    ]
    instance.current_certificate.iam_server_certificate_arn = params[
        "iam_server_certificate_arn"
    ]
    instance.current_certificate.iam_server_certificate_name = params[
        "iam_server_certificate_name"
    ]
