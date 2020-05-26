from datetime import datetime
from typing import List, Dict

import pytest
from botocore.stub import ANY, Stubber

from broker.aws import cloudfront as real_cloudfront
from broker.models import ServiceInstance


class FakeCloudFront:
    # How I would love to use Localstack or Moto instead.  Unfortunately,
    # neither (in the OSS free version) supports Route53 and CloudFront.  So
    # we've been reduced to using the "serviceable" `boto3.stubber`
    def __init__(self, iam_stubber):
        self.stubber = iam_stubber

    def any(self):
        return ANY

    def expect_create_distribution(
        self, service_instance: ServiceInstance, new_distribution_id: str,
    ):
        self.stubber.add_response(
            "create_distribution",
            self._stub_response(
                service_instance.id,
                service_instance.domain_names,
                service_instance.iam_server_certificate_id,
                new_distribution_id,
            ),
            self._stub_request(
                service_instance.id,
                service_instance.domain_names,
                service_instance.iam_server_certificate_id,
            ),
        )

    def _stub_request(
        self,
        service_instance_id: str,
        domains: List[str],
        iam_server_certificate_id: str,
    ):
        return (
            {
                "CallerReference": service_instance_id,
                "Aliases": {"Quantity": len(domains), "Items": domains},
                "DefaultRootObject": "",
                "Origins": {
                    "Quantity": 1,
                    "Items": [
                        {
                            "Id": "default-origin",
                            "DomainName": "external-domain-broker-origin.test.cloud.gov",
                            "CustomOriginConfig": {
                                "HTTPPort": 80,
                                "HTTPSPort": 443,
                                "OriginProtocolPolicy": "https-only",
                                "OriginSslProtocols": {
                                    "Quantity": 1,
                                    "Items": ["TLSv1.2"],
                                },
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
                    "IAMCertificateId": iam_server_certificate_id,
                    "SSLSupportMethod": "sni-only",
                    "MinimumProtocolVersion": "TLSv1.2_2018",
                },
                "IsIPV6Enabled": True,
            },
        )

    def _stub_response(
        self,
        service_instance_id: str,
        domains: List[str],
        iam_server_certificate_id: str,
        new_distribution_id: str,
    ):
        return (
            {
                "Distribution": {
                    "Id": new_distribution_id,
                    "ARN": f"arn:aws:cloudfront::000000000000:distribution/{new_distribution_id}",
                    "Status": "string",
                    "LastModifiedTime": datetime.utcnow(),
                    "InProgressInvalidationBatches": 0,
                    "DomainName": "d111111abcdef8.cloudfront.net",
                    "DistributionConfig": self._stub_request(
                        service_instance_id, domains, iam_server_certificate_id
                    ),
                },
                "Location": f"https://cloudfront.amazonaws.com/2020-05-26/distribution/{new_distribution_id}",
            },
        )


@pytest.fixture(autouse=True)
def cloudfront():
    with Stubber(real_cloudfront) as stubber:
        yield FakeCloudFront(stubber)
        stubber.assert_no_pending_responses()
