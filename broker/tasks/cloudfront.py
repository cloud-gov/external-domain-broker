import logging
import time

from broker.aws import cloudfront
from broker.extensions import config
from broker.lib.tags import add_tag
from broker.models import CDNServiceInstance, CDNDedicatedWAFServiceInstance
from broker.tasks.huey import pipeline_operation

logger = logging.getLogger(__name__)


def get_cookie_policy(service_instance):
    if (
        service_instance.forward_cookie_policy
        == CDNServiceInstance.ForwardCookiePolicy.WHITELIST.value
    ):
        cookies = {
            "Forward": "whitelist",
            "WhitelistedNames": {
                "Quantity": len(service_instance.forwarded_cookies),
                "Items": service_instance.forwarded_cookies,
            },
        }
    else:
        cookies = {"Forward": service_instance.forward_cookie_policy}
    return cookies


def get_header_policy(service_instance):
    return {
        "Quantity": len(service_instance.forwarded_headers),
        "Items": service_instance.forwarded_headers,
    }


def has_default_cookie_and_header_policies(service_instance):
    default_cookie_policy = {"Forward": "all"}
    default_header_policy = {"Quantity": 1, "Items": ["HOST"]}
    return all(
        (
            default_cookie_policy == get_cookie_policy(service_instance),
            default_header_policy == get_header_policy(service_instance),
        )
    )


def get_aliases(service_instance):
    return {
        "Quantity": len(service_instance.domain_names),
        "Items": service_instance.domain_names,
    }


def get_custom_error_responses(service_instance):
    items = []
    for code, page in service_instance.error_responses.items():
        # yes, ErrorCode is an int, and ResponseCode is a str. No, I don't know why.
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudfront.html#CloudFront.Client.create_distribution
        items.append(
            {
                "ErrorCode": int(code),
                "ResponsePagePath": page,
                "ResponseCode": code,
                "ErrorCachingMinTTL": 300,
            }
        )
    if items:
        return {"Quantity": len(items), "Items": items}
    else:
        return {"Quantity": 0}


@pipeline_operation("Creating CloudFront distribution")
def create_distribution(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    certificate = service_instance.new_certificate

    if service_instance.cloudfront_distribution_id:
        try:
            cloudfront.get_distribution(Id=service_instance.cloudfront_distribution_id)
        except cloudfront.exceptions.NoSuchDistribution:
            pass
        else:
            return
    cookies = get_cookie_policy(service_instance)
    distribution_config = {
        "CallerReference": service_instance.id,
        "Aliases": get_aliases(service_instance),
        "DefaultRootObject": "",
        "Origins": {
            "Quantity": 1,
            "Items": [
                {
                    "Id": "default-origin",
                    "DomainName": service_instance.cloudfront_origin_hostname,
                    "OriginPath": service_instance.cloudfront_origin_path,
                    "CustomOriginConfig": {
                        "HTTPPort": 80,
                        "HTTPSPort": 443,
                        "OriginProtocolPolicy": service_instance.origin_protocol_policy,
                        "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
                        "OriginReadTimeout": 30,
                        "OriginKeepaliveTimeout": 5,
                    },
                }
            ],
        },
        "OriginGroups": {"Quantity": 0},
        "DefaultCacheBehavior": {
            "TargetOriginId": "default-origin",
            "ForwardedValues": {
                "QueryString": True,
                "Cookies": cookies,
                "Headers": get_header_policy(service_instance),
                "QueryStringCacheKeys": {"Quantity": 0},
            },
            "TrustedSigners": {"Enabled": False, "Quantity": 0},
            "ViewerProtocolPolicy": "redirect-to-https",
            "MinTTL": 0,
            "AllowedMethods": {
                "Quantity": 7,
                "Items": [
                    "GET",
                    "HEAD",
                    "POST",
                    "PUT",
                    "PATCH",
                    "OPTIONS",
                    "DELETE",
                ],
                "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
            },
            "SmoothStreaming": False,
            "DefaultTTL": 86400,
            "MaxTTL": 31536000,
            "Compress": False,
            "LambdaFunctionAssociations": {"Quantity": 0},
        },
        "CacheBehaviors": {"Quantity": 0},
        "CustomErrorResponses": get_custom_error_responses(service_instance),
        "Comment": "external domain service https://cloud-gov/external-domain-broker",
        "Logging": {
            "Enabled": True,
            "IncludeCookies": False,
            "Bucket": config.CDN_LOG_BUCKET,
            "Prefix": f"{service_instance.id}/",
        },
        "PriceClass": "PriceClass_100",
        "Enabled": True,
        "ViewerCertificate": {
            "CloudFrontDefaultCertificate": False,
            "IAMCertificateId": certificate.iam_server_certificate_id,
            "SSLSupportMethod": "sni-only",
            "MinimumProtocolVersion": "TLSv1.2_2018",
        },
        "IsIPV6Enabled": True,
    }

    tags = service_instance.tags if service_instance.tags else []

    if (
        isinstance(service_instance, CDNDedicatedWAFServiceInstance)
        and service_instance.dedicated_waf_web_acl_arn
    ):
        distribution_config["WebACLId"] = service_instance.dedicated_waf_web_acl_arn
        tags = add_tag(tags, "has_dedicated_acl", "true")

    distribution_config_with_tags = {
        "DistributionConfig": distribution_config,
        "Tags": {
            "Items": tags,
        },
    }

    response = cloudfront.create_distribution_with_tags(
        DistributionConfigWithTags=distribution_config_with_tags
    )

    service_instance.cloudfront_distribution_arn = response["Distribution"]["ARN"]
    service_instance.cloudfront_distribution_id = response["Distribution"]["Id"]
    service_instance.domain_internal = response["Distribution"]["DomainName"]
    service_instance.current_certificate = certificate
    service_instance.new_certificate = None
    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Disabling CloudFront distribution")
def disable_distribution(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if service_instance.cloudfront_distribution_id is None:
        return

    try:
        distribution_config = cloudfront.get_distribution_config(
            Id=service_instance.cloudfront_distribution_id
        )
        distribution_config["DistributionConfig"]["Enabled"] = False
        cloudfront.update_distribution(
            DistributionConfig=distribution_config["DistributionConfig"],
            Id=service_instance.cloudfront_distribution_id,
            IfMatch=distribution_config["ETag"],
        )
    except cloudfront.exceptions.NoSuchDistribution:
        return


@pipeline_operation("Waiting for CloudFront distribution to disable")
def wait_for_distribution_disabled(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if service_instance.cloudfront_distribution_id is None:
        return

    distribution_disabled = False
    num_times = 0
    while not distribution_disabled:
        num_times += 1
        if num_times > config.AWS_POLL_MAX_ATTEMPTS:
            logger.info(
                "Failed to disable distribution",
                extra={
                    "operation_id": operation_id,
                    "cloudfront_distribution_id": service_instance.cloudfront_distribution_id,
                },
            )
            raise RuntimeError("Failed to disable distribution")
        time.sleep(config.AWS_POLL_WAIT_TIME_IN_SECONDS)
        try:
            status = cloudfront.get_distribution(
                Id=service_instance.cloudfront_distribution_id
            )
        except cloudfront.exceptions.NoSuchDistribution:
            return
        distribution_disabled = (
            not status["Distribution"]["DistributionConfig"]["Enabled"]
            and status["Distribution"]["Status"] == "Deployed"
        )


@pipeline_operation("Deleting CloudFront distribution")
def delete_distribution(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if service_instance.cloudfront_distribution_id is None:
        return

    try:
        status = cloudfront.get_distribution(
            Id=service_instance.cloudfront_distribution_id
        )
        cloudfront.delete_distribution(
            Id=service_instance.cloudfront_distribution_id, IfMatch=status["ETag"]
        )
    except cloudfront.exceptions.NoSuchDistribution:
        return


@pipeline_operation("Waiting for CloudFront distribution")
def wait_for_distribution(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    waiter = cloudfront.get_waiter("distribution_deployed")
    waiter.wait(
        Id=service_instance.cloudfront_distribution_id,
        WaiterConfig={
            "Delay": config.AWS_POLL_WAIT_TIME_IN_SECONDS,
            "MaxAttempts": config.AWS_POLL_MAX_ATTEMPTS,
        },
    )


@pipeline_operation("Updating CloudFront distribution certificate")
def update_certificate(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    config = cloudfront.get_distribution_config(
        Id=service_instance.cloudfront_distribution_id
    )
    config["DistributionConfig"]["ViewerCertificate"][
        "IAMCertificateId"
    ] = service_instance.new_certificate.iam_server_certificate_id
    cloudfront.update_distribution(
        DistributionConfig=config["DistributionConfig"],
        Id=service_instance.cloudfront_distribution_id,
        IfMatch=config["ETag"],
    )
    service_instance.current_certificate = service_instance.new_certificate
    service_instance.new_certificate = None
    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Updating CloudFront distribution")
def update_distribution(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    certificate = service_instance.new_certificate

    config_response = cloudfront.get_distribution_config(
        Id=service_instance.cloudfront_distribution_id
    )
    etag = config_response["ETag"]
    config = config_response["DistributionConfig"]
    config["ViewerCertificate"][
        "IAMCertificateId"
    ] = certificate.iam_server_certificate_id
    config["Origins"]["Items"][0][
        "DomainName"
    ] = service_instance.cloudfront_origin_hostname
    config["Origins"]["Items"][0][
        "OriginPath"
    ] = service_instance.cloudfront_origin_path
    config["Origins"]["Items"][0]["CustomOriginConfig"][
        "OriginProtocolPolicy"
    ] = service_instance.origin_protocol_policy
    if "CachePolicyId" in config["DefaultCacheBehavior"]:
        if not has_default_cookie_and_header_policies(service_instance):
            # N.B. This is a really limited workaround. *currently* the only cache policy
            # we're referencing uses
            raise NotImplementedError(
                "Can't set non-default policy with cache-policy ID"
            )
    else:
        config["DefaultCacheBehavior"]["ForwardedValues"]["Cookies"] = (
            get_cookie_policy(service_instance)
        )
        config["DefaultCacheBehavior"]["ForwardedValues"]["Headers"] = (
            get_header_policy(service_instance)
        )
    config["Aliases"] = get_aliases(service_instance)
    config["CustomErrorResponses"] = get_custom_error_responses(service_instance)

    cloudfront.update_distribution(
        DistributionConfig=config,
        Id=service_instance.cloudfront_distribution_id,
        IfMatch=etag,
    )

    service_instance.current_certificate = certificate
    service_instance.new_certificate = None
    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Removing s3 bucket binding")
def remove_s3_bucket_from_cdn_broker_instance(
    operation_id: str, *, operation, db, **kwargs
):
    service_instance = operation.service_instance
    config_response = cloudfront.get_distribution_config(
        Id=service_instance.cloudfront_distribution_id
    )
    etag = config_response["ETag"]
    config = config_response["DistributionConfig"]
    acme_challenge_origin_id = None

    for item in config["CacheBehaviors"].get("Items", []):
        if item["PathPattern"] == "/.well-known/acme-challenge/*":
            acme_challenge_origin_id = item["TargetOriginId"]
    if acme_challenge_origin_id is not None:
        cache_behaviors = {}
        cache_behavior_items = [
            item
            for item in config["CacheBehaviors"]["Items"]
            if item["TargetOriginId"] != acme_challenge_origin_id
        ]
        if cache_behavior_items:
            cache_behaviors["Items"] = cache_behavior_items
        cache_behaviors["Quantity"] = len(cache_behavior_items)
        origins = {}
        origin_items = [
            item
            for item in config["Origins"]["Items"]
            if item["Id"] != acme_challenge_origin_id
        ]
        if origin_items:
            origins["Items"] = origin_items
        origins["Quantity"] = len(origin_items)
        config["Origins"] = origins
        config["CacheBehaviors"] = cache_behaviors
        config["Comment"] = (
            "external domain service https://cloud-gov/external-domain-broker"
        )
        cloudfront.update_distribution(
            DistributionConfig=config,
            Id=service_instance.cloudfront_distribution_id,
            IfMatch=etag,
        )


@pipeline_operation("Adding logging to Cloudfront distribution")
def add_logging_to_bucket(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    config_response = cloudfront.get_distribution_config(
        Id=service_instance.cloudfront_distribution_id
    )
    dist_config = config_response["DistributionConfig"]
    etag = config_response["ETag"]
    if not dist_config["Logging"]["Enabled"]:
        dist_config["Logging"] = {
            "Enabled": True,
            "IncludeCookies": False,
            "Bucket": config.CDN_LOG_BUCKET,
            "Prefix": f"{service_instance.id}/",
        }
        cloudfront.update_distribution(
            DistributionConfig=dist_config,
            Id=service_instance.cloudfront_distribution_id,
            IfMatch=etag,
        )
