import logging
import time

from broker.aws import cloudfront
from broker.extensions import config, db
from broker.models import Operation, CDNServiceInstance
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.retriable_task
def create_distribution(operation_id: int, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    domains = service_instance.domain_names

    operation.step_description = "Creating CloudFront distribution"
    db.session.add(operation)
    db.session.commit()

    if service_instance.cloudfront_distribution_id:
        try:
            cloudfront.get_distribution(Id=service_instance.cloudfront_distribution_id)
        except cloudfront.exceptions.NoSuchDistribution:
            pass
        else:
            return

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

    response = cloudfront.create_distribution(
        DistributionConfig={
            "CallerReference": service_instance.id,
            "Aliases": {"Quantity": len(domains), "Items": domains},
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
                    "Headers": {
                        "Quantity": len(service_instance.forwarded_headers),
                        "Items": service_instance.forwarded_headers,
                    },
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
            "CustomErrorResponses": {"Quantity": 0},
            "Comment": "external domain service https://cloud-gov/external-domain-broker",
            "Logging": {
                "Enabled": False,
                "IncludeCookies": False,
                "Bucket": "",
                "Prefix": "",
            },
            "PriceClass": "PriceClass_100",
            "Enabled": True,
            "ViewerCertificate": {
                "CloudFrontDefaultCertificate": False,
                "IAMCertificateId": service_instance.iam_server_certificate_id,
                "SSLSupportMethod": "sni-only",
                "MinimumProtocolVersion": "TLSv1.2_2018",
            },
            "IsIPV6Enabled": True,
        }
    )

    service_instance.cloudfront_distribution_arn = response["Distribution"]["ARN"]
    service_instance.cloudfront_distribution_id = response["Distribution"]["Id"]
    service_instance.domain_internal = response["Distribution"]["DomainName"]
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def disable_distribution(operation_id: int, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Disabling CloudFront distribution"
    db.session.add(operation)
    db.session.commit()

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


@huey.retriable_task
def wait_for_distribution_disabled(operation_id: int, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    enabled = True
    num_times = 0
    while enabled:
        num_times += 1
        if num_times >= 60:
            logger.info(
                "Failed to disable distribution",
                extra={
                    "operation_id": operation_id,
                    "cloudfront_distribution_id": service_instance.cloudfront_distribution_id,
                },
            )
            raise RuntimeError("Failed to disable distribution")
        time.sleep(config.CLOUDFRONT_PROPAGATION_SLEEP_TIME)
        try:
            status = cloudfront.get_distribution(
                Id=service_instance.cloudfront_distribution_id
            )
        except cloudfront.exceptions.NoSuchDistribution:
            return "No-ETag"
        enabled = status["Distribution"]["DistributionConfig"]["Enabled"]
        etag = status["ETag"]


@huey.retriable_task
def delete_distribution(operation_id: int, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Deleting CloudFront distribution"
    db.session.add(operation)
    db.session.commit()

    try:
        status = cloudfront.get_distribution(
            Id=service_instance.cloudfront_distribution_id
        )
        cloudfront.delete_distribution(
            Id=service_instance.cloudfront_distribution_id, IfMatch=status["ETag"]
        )
    except cloudfront.exceptions.NoSuchDistribution:
        return


@huey.retriable_task
def wait_for_distribution(operation_id: str, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Waiting for CloudFront distribution"
    db.session.add(operation)
    db.session.commit()

    waiter = cloudfront.get_waiter("distribution_deployed")
    waiter.wait(
        Id=service_instance.cloudfront_distribution_id,
        WaiterConfig={
            "Delay": config.AWS_POLL_WAIT_TIME_IN_SECONDS,
            "MaxAttempts": config.AWS_POLL_MAX_ATTEMPTS,
        },
    )


@huey.retriable_task
def update_certificate(operation_id: str, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    config = cloudfront.get_distribution_config(
        Id=service_instance.cloudfront_distribution_id
    )
    config["DistributionConfig"]["ViewerCertificate"][
        "IAMCertificateId"
    ] = service_instance.iam_server_certificate_id
    cloudfront.update_distribution(
        DistributionConfig=config["DistributionConfig"],
        Id=service_instance.cloudfront_distribution_id,
        IfMatch=config["ETag"],
    )
