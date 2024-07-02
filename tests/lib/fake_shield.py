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

    def expect_associate_health_check(self, protection_id: str, health_check_id: str):
        self.stubber.add_response(
            "associate_health_check",
            {},
            {
                "ProtectionId": protection_id,
                "HealthCheckArn": f"arn:aws:route53:::healthcheck/{health_check_id}",
            },
        )

    def expect_disassociate_health_check(
        self, protection_id: str, health_check_id: str
    ):
        self.stubber.add_response(
            "disassociate_health_check",
            {},
            {
                "ProtectionId": protection_id,
                "HealthCheckArn": f"arn:aws:route53:::healthcheck/{health_check_id}",
            },
        )

    def expect_disassociate_health_check_not_found(
        self, protection_id: str, health_check_id: str
    ):
        self.stubber.add_client_error(
            "disassociate_health_check",
            service_error_code="ResourceNotFoundException",
            service_message="Not found",
            http_status_code=404,
            expected_params={
                "ProtectionId": protection_id,
                "HealthCheckArn": f"arn:aws:route53:::healthcheck/{health_check_id}",
            },
        )


@pytest.fixture(autouse=True)
def shield():
    with FakeShield.stubbing(real_shield) as shield_stubber:
        yield shield_stubber
