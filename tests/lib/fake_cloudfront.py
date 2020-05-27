from datetime import datetime
from typing import List, Dict, Any

import pytest

from broker.aws import cloudfront as real_cloudfront
from broker.models import ServiceInstance

from tests.lib.fake_aws import FakeAWS


class FakeCloudFront(FakeAWS):
    def expect_create_distribution(
        self,
        service_instance: ServiceInstance,
        distribution_id: str,
        distribution_hostname: str,
    ):
        self.stubber.add_response(
            "create_distribution",
            self._distribution_response(
                service_instance.id,
                service_instance.domain_names,
                service_instance.iam_server_certificate_id,
                distribution_id,
                distribution_hostname,
            ),
            {
                "DistributionConfig": self._fake_distribution_config(
                    service_instance.id,
                    service_instance.domain_names,
                    service_instance.iam_server_certificate_id,
                )
            },
        )

    def expect_wait_for_distribution(
        self, service_instance: ServiceInstance, distribution_id: str,
    ):
        self.stubber.add_response(
            "get_distribution",
            self._distribution_response(
                service_instance.id,
                service_instance.domain_names,
                service_instance.iam_server_certificate_id,
                distribution_id,
                "ignored",
                "InProgress",
            ),
            {"Id": service_instance.cloudfront_distribution_id},
        )
        self.stubber.add_response(
            "get_distribution",
            self._distribution_response(
                service_instance.id,
                service_instance.domain_names,
                service_instance.iam_server_certificate_id,
                distribution_id,
                "ignored",
                "Deployed",
            ),
            {"Id": service_instance.cloudfront_distribution_id},
        )

    def _fake_distribution_config(
        self, caller_reference: str, domains: List[str], iam_server_certificate_id: str,
    ) -> Dict[str, Any]:
        return {
            "CallerReference": caller_reference,
            "Aliases": {"Quantity": len(domains), "Items": domains},
            "DefaultRootObject": "",
            "Origins": {
                "Quantity": 1,
                "Items": [
                    {
                        "Id": "default-origin",
                        "DomainName": "cloud.local",
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
        }

    def _distribution_response(
        self,
        caller_reference: str,
        domains: List[str],
        iam_server_certificate_id: str,
        distribution_id: str,
        distribution_hostname: str,
        status: str = "InProgress",
    ) -> Dict[str, Any]:
        return {
            "Distribution": {
                "Id": distribution_id,
                "ARN": f"arn:aws:cloudfront::000000000000:distribution/{distribution_id}",
                "Status": status,
                "LastModifiedTime": datetime.utcnow(),
                "InProgressInvalidationBatches": 0,
                "DomainName": distribution_hostname,
                "ActiveTrustedSigners": {"Enabled": False, "Quantity": 0, "Items": []},
                "DistributionConfig": self._fake_distribution_config(
                    caller_reference, domains, iam_server_certificate_id
                ),
            }
        }


@pytest.fixture(autouse=True)
def cloudfront():
    with FakeCloudFront.stubbing(real_cloudfront) as cloudfront_stubber:
        yield cloudfront_stubber
