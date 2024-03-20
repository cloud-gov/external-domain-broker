from datetime import datetime
import pytest

from broker.aws import alb as real_alb
from tests.lib.fake_aws import FakeAWS


class FakeALB(FakeAWS):
    def expect_get_listeners(self, listener_arn):
        certificates = [{"CertificateArn": "certificate-arn", "IsDefault": True}]
        self.stubber.add_response(
            "describe_listeners",
            {
                "Listeners": [
                    {
                        "ListenerArn": listener_arn,
                        "LoadBalancerArn": f"alb-{listener_arn}",
                        "Port": 123,
                        "Protocol": "HTTPS",
                        "Certificates": certificates,
                        "SslPolicy": "string",
                        "DefaultActions": [
                            {
                                "Type": "forward",
                                "TargetGroupArn": "string",
                                "Order": 1,
                                "ForwardConfig": {
                                    "TargetGroups": [
                                        {"TargetGroupArn": "string", "Weight": 1}
                                    ],
                                    "TargetGroupStickinessConfig": {"Enabled": False},
                                },
                            }
                        ],
                    }
                ],
                "NextMarker": "string",
            },
            {"ListenerArns": [listener_arn]},
        )

    def expect_get_certificates_for_listener(
        self, listener_arn, num_certificates=0, certificates=[]
    ):
        if len(certificates) == 0 and num_certificates > 0:
            certificates = [
                {"CertificateArn": f"{listener_arn}/certificate-arn", "IsDefault": True}
            ]
            for i in range(num_certificates):
                certificates.append(
                    {
                        "CertificateArn": f"{listener_arn}/certificate-arn-{i}",
                        "IsDefault": False,
                    }
                )
        self.stubber.add_response(
            "describe_listener_certificates",
            {"Certificates": certificates},
            {"ListenerArn": listener_arn},
        )

    def expect_add_certificate_to_listener(self, listener_arn, iam_cert_arn):
        self.stubber.add_response(
            "add_listener_certificates",
            {
                "Certificates": [
                    {"CertificateArn": "arn:2", "IsDefault": True},
                    {"CertificateArn": iam_cert_arn, "IsDefault": False},
                ]
            },
            {
                "ListenerArn": listener_arn,
                "Certificates": [{"CertificateArn": iam_cert_arn}],
            },
        )

    def expect_remove_certificate_from_listener(self, listener_arn, iam_cert_arn):
        self.stubber.add_response(
            "remove_listener_certificates",
            {},
            {
                "ListenerArn": listener_arn,
                "Certificates": [{"CertificateArn": iam_cert_arn}],
            },
        )

    def expect_describe_alb(
        self, alb_arn, returned_domain: str = "somedomain.cloud.test"
    ):
        self.stubber.add_response(
            "describe_load_balancers",
            {
                "LoadBalancers": [
                    {
                        "LoadBalancerArn": "alb_arn",
                        "DNSName": returned_domain,
                        "CanonicalHostedZoneId": "ALBHOSTEDZONEID",
                        "CreatedTime": datetime(2015, 1, 1),
                        "LoadBalancerName": "string",
                        "Scheme": "internet-facing",
                        "VpcId": "string",
                        "State": {"Code": "active", "Reason": "string"},
                        "Type": "application",
                        "AvailabilityZones": [
                            {
                                "ZoneName": "string",
                                "SubnetId": "string",
                                "LoadBalancerAddresses": [
                                    {
                                        "IpAddress": "string",
                                        "AllocationId": "string",
                                        "PrivateIPv4Address": "string",
                                    }
                                ],
                            }
                        ],
                        "SecurityGroups": ["string"],
                        "IpAddressType": "ipv4",
                    }
                ],
                "NextMarker": "string",
            },
            {"LoadBalancerArns": [alb_arn]},
        )


@pytest.fixture(autouse=True)
def alb():
    with FakeALB.stubbing(real_alb) as alb_stubber:
        yield alb_stubber
