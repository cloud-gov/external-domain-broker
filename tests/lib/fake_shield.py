import pytest

from broker.aws import shield as real_shield
from tests.lib.fake_aws import FakeAWS


class FakeShield(FakeAWS):
    def expect_list_protections(self, protection_id: str, cloudfront_arn: str):
        method = "list_protections"
        request = {
            "InclusionFilters": {"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]},
        }
        response = {
            "Protections": [
                {
                    "ResourceArn": cloudfront_arn,
                    "Id": protection_id,
                }
            ]
        }
        self.stubber.add_response(method, response, request)


@pytest.fixture(autouse=True)
def shield():
    with FakeShield.stubbing(real_shield) as shield_stubber:
        yield shield_stubber
