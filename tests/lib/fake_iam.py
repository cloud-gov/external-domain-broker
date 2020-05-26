from datetime import datetime, timezone, timedelta

import pytest
from botocore.stub import ANY, Stubber

from broker.aws import iam as real_iam


class FakeIAM:
    # How I would love to use Localstack or Moto instead.  Unfortunately,
    # neither (in the OSS free version) supports Route53 and CloudFront.  So
    # we've been reduced to using the "serviceable" `boto3.stubber`
    def __init__(self, iam_stubber):
        self.stubber = iam_stubber

    def any(self):
        return ANY

    def expect_certificate_upload(
        self, path: str, name: str, cert: str, private_key: str, chain: str
    ):
        now = datetime.now(timezone.utc)
        three_months_from_now = now + timedelta(90)
        self.stubber.add_response(
            "upload_server_certificate",
            {
                "ServerCertificateMetadata": {
                    "ServerCertificateId": "FAKE_CERT_ID_XXXXXXXX",
                    "Path": "/cloudfront/external-service-broker-test/",
                    "ServerCertificateName": "cert-name",
                    "Arn": "arn:aws:iam::000000000000:server-certificate/cloudfront/external-service-broker-test/cert-name",
                    "UploadDate": now,
                    "Expiration": three_months_from_now,
                }
            },
            {
                "Path": path,
                "ServerCertificateName": name,
                "CertificateBody": cert,
                "PrivateKey": private_key,
                "CertificateChain": chain,
            },
        )


@pytest.fixture(autouse=True)
def iam():
    with Stubber(real_iam) as stubber:
        yield FakeIAM(stubber)
        stubber.assert_no_pending_responses()
