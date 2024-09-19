import pytest


from broker.aws import sns_commercial as real_sns_commercial
from broker.extensions import config

from tests.lib.fake_aws import FakeAWS


class FakeSNS(FakeAWS):
    def expect_create_topic(self, service_instance):
        topic_name = f"{config.AWS_RESOURCE_PREFIX}-{service_instance.id}-notifications"
        request = {
            "Name": topic_name,
        }
        if service_instance.tags:
            request["Tags"] = service_instance.tags
        self.stubber.add_response(
            "create_topic",
            {"TopicArn": f"{service_instance.id}-notifications-arn"},
            request,
        )

    def expect_delete_topic(self, topic_arn):
        self.stubber.add_response(
            "delete_topic",
            {},
            {"TopicArn": topic_arn},
        )

    def expect_delete_topic_not_found(self, topic_arn):
        self.stubber.add_client_error(
            "delete_topic",
            service_error_code="NotFoundException",
            service_message="Not found",
            http_status_code=404,
            expected_params={"TopicArn": topic_arn},
        )


@pytest.fixture(autouse=True)
def sns_commercial():
    with FakeSNS.stubbing(real_sns_commercial) as sns_stubber:
        yield sns_stubber
