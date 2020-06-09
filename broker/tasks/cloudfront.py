import logging
import time

from broker.aws import cloudfront
from broker.extensions import config
from broker.models import Operation
from broker.tasks import huey
from broker.tasks.db_injection import inject_db

logger = logging.getLogger(__name__)


@huey.retriable_task
@inject_db
def create_distribution(operation_id: int, **kwargs):
    db = kwargs["db"]
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    domains = service_instance.domain_names

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
                            "OriginProtocolPolicy": "https-only",
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
                    "Cookies": {"Forward": "all"},
                    "Headers": {"Quantity": 1, "Items": ["HOST"]},
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
    service_instance.cloudfront_distribution_url = response["Distribution"][
        "DomainName"
    ]
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
@inject_db
def disable_distribution(operation_id: int, **kwargs):
    db = kwargs["db"]
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

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
@inject_db
def wait_for_distribution_disabled(operation_id: int, **kwargs):
    db = kwargs["db"]
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
            return
        enabled = status["Distribution"]["DistributionConfig"]["Enabled"]


@huey.retriable_task
@inject_db
def delete_distribution(operation_id: int, **kwargs):
    db = kwargs["db"]
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    try:
        cloudfront.delete_distribution(Id=service_instance.cloudfront_distribution_id)
    except cloudfront.exceptions.NoSuchDistribution:
        return


@huey.retriable_task
@inject_db
def wait_for_distribution(operation_id: str, **kwargs):
    db = kwargs["db"]
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    waiter = cloudfront.get_waiter("distribution_deployed")
    waiter.wait(
        Id=service_instance.cloudfront_distribution_id,
        WaiterConfig={
            "Delay": config.AWS_POLL_WAIT_TIME_IN_SECONDS,
            "MaxAttempts": config.AWS_POLL_MAX_ATTEMPTS,
        },
    )
