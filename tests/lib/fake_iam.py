from datetime import datetime, timedelta, timezone

import pytest

from broker.aws import iam_commercial as real_iam_c
from broker.aws import iam_govcloud as real_iam_g
from tests.lib.fake_aws import FakeAWS


class FakeIAM(FakeAWS):
    def expect_upload_server_certificate(
        self, name: str, cert: str, private_key: str, chain: str, path: str
    ):
        now = datetime.now(timezone.utc)
        three_months_from_now = now + timedelta(90)
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
                "Arn": f"arn:aws:iam::000000000000:server-certificate{path}{name}",
                "UploadDate": now,
                "Expiration": three_months_from_now,
            }
        }
        self.stubber.add_response(method, response, request)

    def expect_upload_server_certificate_raising_duplicate(
        self, name: str, cert: str, private_key: str, chain: str, path: str
    ):
        self.stubber.add_client_error(
            "upload_server_certificate",
            service_error_code="EntityAlreadyExistsException",
            service_message="already got one",
            expected_params={
                "Path": path,
                "ServerCertificateName": name,
                "CertificateBody": cert,
                "PrivateKey": private_key,
                "CertificateChain": chain,
            },
        )

    def expects_delete_server_certificate(self, name: str):
        self.stubber.add_response(
            "delete_server_certificate", {}, {"ServerCertificateName": name}
        )

    def expects_delete_server_certificate_returning_no_such_entity(self, name: str):
        self.stubber.add_client_error(
            "delete_server_certificate",
            service_error_code="NoSuchEntity",
            service_message="'Ain't there.",
            http_status_code=404,
            expected_params={"ServerCertificateName": name},
        )

    def expects_delete_server_certificate_returning_unexpected_error(self, name: str):
        self.stubber.add_client_error(
            "delete_server_certificate",
            service_error_code="UnexpectedError",
            service_message="Unexpected error",
            http_status_code=500,
            expected_params={"ServerCertificateName": name},
        )


@pytest.fixture(autouse=True)
def iam_commercial():
    with FakeIAM.stubbing(real_iam_c) as iam_stubber:
        yield iam_stubber


@pytest.fixture(autouse=True)
def iam_govcloud():
    with FakeIAM.stubbing(real_iam_g) as iam_stubber:
        yield iam_stubber
