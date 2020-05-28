from datetime import datetime, timezone, timedelta

import pytest
from broker.aws import iam as real_iam

from tests.lib.fake_aws import FakeAWS


class FakeIAM(FakeAWS):
    def expect_certificate_upload(
        self, name: str, cert: str, private_key: str, chain: str
    ):
        now = datetime.now(timezone.utc)
        three_months_from_now = now + timedelta(90)
        path = "/cloudfront/external-domain-broker/test"
        method = "upload_server_certificate"
        request = {
            "Path": path,
            "ServerCertificateName": name,
            "CertificateBody": cert,
            "PrivateKey": private_key,
            "CertificateChain": chain,
        }
        response = {
            "ServerCertificateMetadata": {
                "ServerCertificateId": "FAKE_CERT_ID_XXXXXXXX",
                "Path": path,
                "ServerCertificateName": name,
                "Arn": f"arn:aws:iam::000000000000:server-certificate{path}/{name}",
                "UploadDate": now,
                "Expiration": three_months_from_now,
            }
        }
        self.stubber.add_response(method, response, request)


@pytest.fixture(autouse=True)
def iam():
    with FakeIAM.stubbing(real_iam) as iam_stubber:
        yield iam_stubber
