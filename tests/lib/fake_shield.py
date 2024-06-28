import pytest
from typing import Dict, List, TypedDict, NotRequired

from broker.aws import shield as real_shield
from tests.lib.fake_aws import FakeAWS


class Protection(TypedDict):
    ResourceArn: str
    Id: str


class ListProtectionRequest(TypedDict):
    InclusionFilters: Dict
    NextToken: NotRequired[str]


class ListProtectionResponse(TypedDict):
    Protections: List[Protection]
    NextToken: NotRequired[str]


class FakeShield(FakeAWS):
    def expect_list_protections(self, *protections_list: List[Protection]):
        method = "list_protections"
        response_number = 0
        next_token = ""

        for protections in protections_list:
            request: ListProtectionRequest = {
                "InclusionFilters": {"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]},
            }
            response: ListProtectionResponse = {"Protections": protections}

            if response_number < len(protections_list):
                if next_token:
                    request["NextToken"] = next_token
                next_token = f"next-{response_number}"

            if response_number < (len(protections_list) - 1):
                response["NextToken"] = next_token
                response_number += 1

            self.stubber.add_response(method, response, request)


@pytest.fixture(autouse=True)
def shield():
    with FakeShield.stubbing(real_shield) as shield_stubber:
        yield shield_stubber
