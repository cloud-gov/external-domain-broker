from datetime import datetime
from typing import Any, Dict, List

import pytest

from broker.aws import cloudfront as real_cloudfront
from broker.lib.tags import add_tag
from tests.lib.fake_aws import FakeAWS


class FakeCloudFront(FakeAWS):
    def expect_create_distribution_with_tags(
        self,
        caller_reference: str,
        domains: List[str],
        certificate_id: str,
        origin_hostname: str,
        origin_path: str,
        distribution_id: str,
        distribution_hostname: str,
        forward_cookie_policy: str = "all",
        forwarded_cookies: list = None,
        forwarded_headers: list = None,
        origin_protocol_policy: str = "https-only",
        bucket_prefix: str = "",
        custom_error_responses: dict = None,
        dedicated_waf_web_acl_arn: str = "",
    ):
        if custom_error_responses is None:
            custom_error_responses = {"Quantity": 0}
        if forwarded_headers is None:
            forwarded_headers = ["HOST"]
        self.stubber.add_response(
            "create_distribution_with_tags",
            self._distribution_response(
                caller_reference,
                domains,
                certificate_id,
                origin_hostname,
                origin_path,
                distribution_id,
                distribution_hostname,
                forward_cookie_policy=forward_cookie_policy,
                forwarded_cookies=forwarded_cookies,
                forwarded_headers=forwarded_headers,
                origin_protocol_policy=origin_protocol_policy,
                bucket_prefix=bucket_prefix,
                custom_error_responses=custom_error_responses,
            ),
            {
                "DistributionConfigWithTags": self._distribution_config_with_tags(
                    caller_reference,
                    domains,
                    certificate_id,
                    origin_hostname,
                    origin_path,
                    forward_cookie_policy=forward_cookie_policy,
                    forwarded_cookies=forwarded_cookies,
                    forwarded_headers=forwarded_headers,
                    origin_protocol_policy=origin_protocol_policy,
                    bucket_prefix=bucket_prefix,
                    custom_error_responses=custom_error_responses,
                    dedicated_waf_web_acl_arn=dedicated_waf_web_acl_arn,
                ),
            },
        )

    def expect_get_distribution_config(
        self,
        caller_reference: str,
        domains: List[str],
        certificate_id: str,
        origin_hostname: str,
        origin_path: str,
        distribution_id: str,
        forward_cookie_policy: str = "all",
        forwarded_cookies: list = None,
        forwarded_headers: list = None,
        origin_protocol_policy: str = "https-only",
        bucket_prefix: str = "",
        custom_error_responses: str = None,
        include_le_bucket: bool = False,
        include_log_bucket: bool = True,
    ):
        if custom_error_responses is None:
            custom_error_responses = {"Quantity": 0}
        if forwarded_headers is None:
            forwarded_headers = ["HOST"]
        self.etag = str(datetime.now().timestamp())
        self.stubber.add_response(
            "get_distribution_config",
            {
                "DistributionConfig": self._distribution_config(
                    caller_reference,
                    domains,
                    certificate_id,
                    origin_hostname,
                    origin_path,
                    forward_cookie_policy=forward_cookie_policy,
                    forwarded_cookies=forwarded_cookies,
                    forwarded_headers=forwarded_headers,
                    origin_protocol_policy=origin_protocol_policy,
                    bucket_prefix=bucket_prefix,
                    custom_error_responses=custom_error_responses,
                    include_le_bucket=include_le_bucket,
                    include_log_bucket=include_log_bucket,
                ),
                "ETag": self.etag,
            },
            {"Id": distribution_id},
        )

    def expect_get_distribution_config_returning_no_such_distribution(
        self, distribution_id: str
    ):
        self.stubber.add_client_error(
            "get_distribution_config",
            service_error_code="NoSuchDistribution",
            service_message="'Ain't there.",
            http_status_code=404,
            expected_params={"Id": distribution_id},
        )

    def expect_disable_distribution(
        self,
        caller_reference: str,
        domains: List[str],
        certificate_id: str,
        origin_hostname: str,
        origin_path: str,
        distribution_id: str,
        distribution_hostname: str,
    ):
        self.stubber.add_response(
            "update_distribution",
            self._distribution_response(
                caller_reference,
                domains,
                certificate_id,
                origin_hostname,
                origin_path,
                distribution_id,
                distribution_hostname,
                custom_error_responses={"Quantity": 0},
            ),
            {
                "DistributionConfig": self._distribution_config(
                    caller_reference,
                    domains,
                    certificate_id,
                    origin_hostname,
                    origin_path,
                    enabled=False,
                    custom_error_responses={"Quantity": 0},
                ),
                "Id": distribution_id,
                "IfMatch": self.etag,
            },
        )

    def expect_delete_distribution(self, distribution_id: str):
        self.stubber.add_response(
            "delete_distribution", {}, {"Id": distribution_id, "IfMatch": self.etag}
        )

    def expect_delete_distribution_returning_no_such_distribution(
        self, distribution_id: str
    ):
        self.stubber.add_client_error(
            "delete_distribution",
            service_error_code="NoSuchDistribution",
            service_message="'Ain't there.",
            http_status_code=404,
            expected_params={"Id": distribution_id, "IfMatch": "No-ETag"},
        )

    def expect_get_distribution(
        self,
        caller_reference: str,
        domains: List[str],
        certificate_id: str,
        origin_hostname: str,
        origin_path: str,
        distribution_id: str,
        status: str,
        enabled: bool = True,
        forward_cookie_policy: str = "all",
        forwarded_cookies: list = None,
        forwarded_headers: list = None,
        origin_protocol_policy: str = "https-only",
        bucket_prefix: str = "",
        custom_error_responses: dict = None,
        include_le_bucket: bool = False,
    ):
        if custom_error_responses is None:
            custom_error_responses = {"Quantity": 0}
        if forwarded_headers is None:
            forwarded_headers = ["HOST"]
        self.etag = str(datetime.now().timestamp())
        distribution = self._distribution_response(
            caller_reference,
            domains,
            certificate_id,
            origin_hostname,
            origin_path,
            distribution_id,
            "ignored",
            status,
            enabled,
            forward_cookie_policy=forward_cookie_policy,
            forwarded_cookies=forwarded_cookies,
            forwarded_headers=forwarded_headers,
            origin_protocol_policy=origin_protocol_policy,
            bucket_prefix=bucket_prefix,
            custom_error_responses=custom_error_responses,
            include_le_bucket=include_le_bucket,
        )
        distribution["ETag"] = self.etag
        self.stubber.add_response(
            "get_distribution", distribution, {"Id": distribution_id}
        )

    def expect_get_distribution_returning_no_such_distribution(
        self, distribution_id: str
    ):
        self.stubber.add_client_error(
            "get_distribution",
            service_error_code="NoSuchDistribution",
            service_message="'Ain't there.",
            http_status_code=404,
            expected_params={"Id": distribution_id},
        )

    def expect_update_distribution(
        self,
        caller_reference: str,
        domains: List[str],
        certificate_id: str,
        origin_hostname: str,
        origin_path: str,
        distribution_id: str,
        distribution_hostname: str,
        forward_cookie_policy: str = "all",
        forwarded_cookies: list = None,
        forwarded_headers: list = None,
        origin_protocol_policy: str = "https-only",
        bucket_prefix: str = "",
        custom_error_responses: dict = None,
    ):
        if custom_error_responses is None:
            custom_error_responses = {"Quantity": 0}
        if forwarded_headers is None:
            forwarded_headers = ["HOST"]
        self.stubber.add_response(
            "update_distribution",
            self._distribution_response(
                caller_reference,
                domains,
                certificate_id,
                origin_hostname,
                origin_path,
                distribution_id,
                distribution_hostname,
                forward_cookie_policy=forward_cookie_policy,
                forwarded_cookies=forwarded_cookies,
                forwarded_headers=forwarded_headers,
                origin_protocol_policy=origin_protocol_policy,
                bucket_prefix=bucket_prefix,
                custom_error_responses=custom_error_responses,
            ),
            {
                "DistributionConfig": self._distribution_config(
                    caller_reference,
                    domains,
                    certificate_id,
                    origin_hostname,
                    origin_path,
                    forward_cookie_policy=forward_cookie_policy,
                    forwarded_cookies=forwarded_cookies,
                    forwarded_headers=forwarded_headers,
                    origin_protocol_policy=origin_protocol_policy,
                    bucket_prefix=bucket_prefix,
                    custom_error_responses=custom_error_responses,
                ),
                "Id": distribution_id,
                "IfMatch": self.etag,
            },
        )

    def _distribution_config(
        self,
        caller_reference: str,
        domains: List[str],
        iam_server_certificate_id: str,
        origin_hostname: str,
        origin_path: str,
        enabled: bool = True,
        forward_cookie_policy: str = "all",
        forwarded_cookies: list = None,
        forwarded_headers: list = None,
        origin_protocol_policy: str = "https-only",
        bucket_prefix: str = "",
        custom_error_responses: dict = None,
        include_le_bucket: bool = False,
        include_log_bucket: bool = True,
        dedicated_waf_web_acl_arn: str = "",
    ) -> Dict[str, Any]:
        if forwarded_headers is None:
            forwarded_headers = ["HOST"]
        cookies = {"Forward": forward_cookie_policy}
        if forward_cookie_policy == "whitelist":
            cookies["WhitelistedNames"] = {
                "Quantity": len(forwarded_cookies),
                "Items": forwarded_cookies,
            }
        distribution_config = {
            "CallerReference": caller_reference,
            "Aliases": {"Quantity": len(domains), "Items": domains},
            "DefaultRootObject": "",
            "Origins": {
                "Quantity": 1,
                "Items": [
                    {
                        "Id": "default-origin",
                        "DomainName": origin_hostname,
                        "OriginPath": origin_path,
                        "CustomOriginConfig": {
                            "HTTPPort": 80,
                            "HTTPSPort": 443,
                            "OriginProtocolPolicy": origin_protocol_policy,
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
                        "Quantity": len(forwarded_headers),
                        "Items": forwarded_headers,
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
            "CustomErrorResponses": custom_error_responses,
            "Comment": "external domain service https://cloud-gov/external-domain-broker",
            "PriceClass": "PriceClass_100",
            "Enabled": enabled,
            "ViewerCertificate": {
                "CloudFrontDefaultCertificate": False,
                "IAMCertificateId": iam_server_certificate_id,
                "SSLSupportMethod": "sni-only",
                "MinimumProtocolVersion": "TLSv1.2_2018",
            },
            "IsIPV6Enabled": True,
        }
        if include_le_bucket:
            distribution_config["Origins"]["Quantity"] += 1
            distribution_config["Origins"]["Items"].append(
                {
                    "Id": "s3-cdn-broker-le-test-some-other-stuff",
                    "DomainName": "cdn-broker-le-test.s3.amazonaws.com",
                    "OriginPath": "",
                    "CustomHeaders": {"Quantity": 0},
                    "S3OriginConfig": {"OriginAccessIdentity": ""},
                }
            )
            distribution_config["CacheBehaviors"] = {
                "Quantity": 1,
                "Items": [
                    {
                        "PathPattern": "/.well-known/acme-challenge/*",
                        "TargetOriginId": "s3-cdn-broker-le-test-some-other-stuff",
                        "ForwardedValues": {
                            "QueryString": False,
                            "Cookies": {"Forward": "none"},
                            "Headers": {"Quantity": 0},
                            "QueryStringCacheKeys": {"Quantity": 0},
                        },
                        "TrustedSigners": {"Enabled": False, "Quantity": 0},
                        "ViewerProtocolPolicy": "allow-all",
                        "MinTTL": 0,
                        "AllowedMethods": {
                            "Quantity": 2,
                            "Items": ["HEAD", "GET"],
                            "CachedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"]},
                        },
                        "SmoothStreaming": False,
                        "DefaultTTL": 86400,
                        "MaxTTL": 31536000,
                        "Compress": False,
                        "LambdaFunctionAssociations": {"Quantity": 0},
                        "FieldLevelEncryptionId": "",
                    }
                ],
            }
        if include_log_bucket:
            distribution_config["Logging"] = {
                "Enabled": True,
                "IncludeCookies": False,
                "Bucket": "mybucket.s3.amazonaws.com",
                "Prefix": bucket_prefix,
            }
        else:
            distribution_config["Logging"] = {
                "Enabled": False,
                "IncludeCookies": False,
                "Bucket": "",
                "Prefix": "",
            }
        return distribution_config

    def _distribution_config_with_tags(
        self,
        caller_reference: str,
        domains: List[str],
        iam_server_certificate_id: str,
        origin_hostname: str,
        origin_path: str,
        enabled: bool = True,
        forward_cookie_policy: str = "all",
        forwarded_cookies: list = None,
        forwarded_headers: list = None,
        origin_protocol_policy: str = "https-only",
        bucket_prefix: str = "",
        custom_error_responses: dict = None,
        include_le_bucket: bool = False,
        include_log_bucket: bool = True,
        dedicated_waf_web_acl_arn: str = "",
    ) -> Dict[str, Any]:
        if forwarded_headers is None:
            forwarded_headers = ["HOST"]
        cookies = {"Forward": forward_cookie_policy}
        if forward_cookie_policy == "whitelist":
            cookies["WhitelistedNames"] = {
                "Quantity": len(forwarded_cookies),
                "Items": forwarded_cookies,
            }
        distribution_config = {
            "CallerReference": caller_reference,
            "Aliases": {"Quantity": len(domains), "Items": domains},
            "DefaultRootObject": "",
            "Origins": {
                "Quantity": 1,
                "Items": [
                    {
                        "Id": "default-origin",
                        "DomainName": origin_hostname,
                        "OriginPath": origin_path,
                        "CustomOriginConfig": {
                            "HTTPPort": 80,
                            "HTTPSPort": 443,
                            "OriginProtocolPolicy": origin_protocol_policy,
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
                        "Quantity": len(forwarded_headers),
                        "Items": forwarded_headers,
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
            "CustomErrorResponses": custom_error_responses,
            "Comment": "external domain service https://cloud-gov/external-domain-broker",
            "PriceClass": "PriceClass_100",
            "Enabled": enabled,
            "ViewerCertificate": {
                "CloudFrontDefaultCertificate": False,
                "IAMCertificateId": iam_server_certificate_id,
                "SSLSupportMethod": "sni-only",
                "MinimumProtocolVersion": "TLSv1.2_2018",
            },
            "IsIPV6Enabled": True,
        }
        if include_le_bucket:
            distribution_config["Origins"]["Quantity"] += 1
            distribution_config["Origins"]["Items"].append(
                {
                    "Id": "s3-cdn-broker-le-test-some-other-stuff",
                    "DomainName": "cdn-broker-le-test.s3.amazonaws.com",
                    "OriginPath": "",
                    "CustomHeaders": {"Quantity": 0},
                    "S3OriginConfig": {"OriginAccessIdentity": ""},
                }
            )
            distribution_config["CacheBehaviors"] = {
                "Quantity": 1,
                "Items": [
                    {
                        "PathPattern": "/.well-known/acme-challenge/*",
                        "TargetOriginId": "s3-cdn-broker-le-test-some-other-stuff",
                        "ForwardedValues": {
                            "QueryString": False,
                            "Cookies": {"Forward": "none"},
                            "Headers": {"Quantity": 0},
                            "QueryStringCacheKeys": {"Quantity": 0},
                        },
                        "TrustedSigners": {"Enabled": False, "Quantity": 0},
                        "ViewerProtocolPolicy": "allow-all",
                        "MinTTL": 0,
                        "AllowedMethods": {
                            "Quantity": 2,
                            "Items": ["HEAD", "GET"],
                            "CachedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"]},
                        },
                        "SmoothStreaming": False,
                        "DefaultTTL": 86400,
                        "MaxTTL": 31536000,
                        "Compress": False,
                        "LambdaFunctionAssociations": {"Quantity": 0},
                        "FieldLevelEncryptionId": "",
                    }
                ],
            }
        if include_log_bucket:
            distribution_config["Logging"] = {
                "Enabled": True,
                "IncludeCookies": False,
                "Bucket": "mybucket.s3.amazonaws.com",
                "Prefix": bucket_prefix,
            }
        else:
            distribution_config["Logging"] = {
                "Enabled": False,
                "IncludeCookies": False,
                "Bucket": "",
                "Prefix": "",
            }
        tags = {}
        if dedicated_waf_web_acl_arn:
            distribution_config["WebACLId"] = dedicated_waf_web_acl_arn
            tags = add_tag(tags, "has_dedicated_acl", "true")
        distribution_config_with_tags = {
            "DistributionConfig": distribution_config,
            "Tags": tags,
        }
        return distribution_config_with_tags

    def _distribution_response(
        self,
        caller_reference: str,
        domains: List[str],
        iam_server_certificate_id: str,
        origin_hostname: str,
        origin_path: str,
        distribution_id: str,
        distribution_hostname: str,
        status: str = "InProgress",
        enabled: bool = True,
        forward_cookie_policy: str = "all",
        forwarded_cookies: list = None,
        forwarded_headers: list = None,
        origin_protocol_policy: str = "https-only",
        bucket_prefix: str = "",
        custom_error_responses: dict = None,
        include_le_bucket: bool = False,
        dedicated_waf_web_acl_arn: str = "",
    ) -> Dict[str, Any]:
        if forwarded_headers is None:
            forwarded_headers = ["HOST"]
        cookies = {"Forward": forward_cookie_policy}
        if forward_cookie_policy == "whitelist":
            cookies["WhitelistedNames"] = {
                "Quantity": len(forwarded_cookies),
                "Items": forwarded_cookies,
            }
        return {
            "Distribution": {
                "Id": distribution_id,
                "ARN": f"arn:aws:cloudfront::000000000000:distribution/{distribution_id}",
                "Status": status,
                "LastModifiedTime": datetime.utcnow(),
                "InProgressInvalidationBatches": 0,
                "DomainName": distribution_hostname,
                "ActiveTrustedSigners": {"Enabled": False, "Quantity": 0, "Items": []},
                "DistributionConfig": self._distribution_config(
                    caller_reference,
                    domains,
                    iam_server_certificate_id,
                    origin_hostname,
                    origin_path,
                    enabled,
                    forward_cookie_policy,
                    forwarded_cookies,
                    forwarded_headers,
                    origin_protocol_policy,
                    bucket_prefix,
                    custom_error_responses,
                    include_le_bucket,
                    dedicated_waf_web_acl_arn,
                ),
            }
        }

    def _tags(
        self,
        dedicated_waf_web_acl_arn: str = "",
    ) -> Dict[str, Any]:
        tags = {}
        if dedicated_waf_web_acl_arn:
            tags["has_dedicated_acl"] = "true"
        return tags


@pytest.fixture(autouse=True)
def cloudfront():
    with FakeCloudFront.stubbing(real_cloudfront) as cloudfront_stubber:
        yield cloudfront_stubber
