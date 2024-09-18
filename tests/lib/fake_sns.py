import pytest


from broker.aws import sns_commercial as real_sns_commercial

from tests.lib.fake_aws import FakeAWS


class FakeSNS(FakeAWS):
    def expect_create_topic(self, topic_name: str, tags):
        request = {
            "TopicName": topic_name,
        }
        if tags:
            request["Tags"] = tags
        self.stubber.add_response(
            "create_topic",
            {},
            request,
        )


@pytest.fixture(autouse=True)
def sns_commercial():
    with FakeSNS.stubbing(real_sns_commercial) as sns_stubber:
        yield sns_stubber
