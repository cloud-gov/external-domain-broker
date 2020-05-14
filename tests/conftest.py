import re
import pytest
from botocore.stub import Stubber, ANY
from broker.aws import route53 as real_route53
from broker.config import config_from_env
from datetime import datetime, timezone


def pytest_configure(config):
    config.addinivalue_line("markers", "focus: Only run this test.")


def pytest_collection_modifyitems(items, config):
    """
    Focus on tests marked focus, if any.  Run all
    otherwise.
    """

    selected_items = []
    deselected_items = []

    focused = False

    for item in items:
        if item.get_closest_marker("focus"):
            focused = True
            selected_items.append(item)
        else:
            deselected_items.append(item)

    if focused:
        print("\nOnly running @pytest.mark.focus tests")
        config.hook.pytest_deselected(items=deselected_items)
        items[:] = selected_items


class SimpleRegex:
    """
    Helper for simplifying regex assertions

    Use like such:

    assert "some\nmultiline\nstring" == simple_regex(r'some multiline')
    """

    def __init__(self, pattern):
        pattern = pattern.replace(" ", "\\s")
        self._regex = re.compile(pattern, re.MULTILINE | re.DOTALL)

    def __eq__(self, actual):
        return bool(self._regex.search(actual))

    def __repr__(self):
        return self._regex.pattern


@pytest.fixture
def simple_regex():
    def _simple_regex(pattern):
        return SimpleRegex(pattern)

    return _simple_regex


class FakeRoute53:
    # How I would love to use Localstack or Moto instead.  Unfortunately,
    # neither (in the OSS free version) supports Route53 and CloudFront.  So
    # we've been reduced to using the "serviceable" `boto3.stubber`
    def __init__(self, route53_stubber):
        self.stubber = route53_stubber

    def any(self):
        return ANY

    def expect_create_txt_for(self, domain):
        submitted_at = datetime.now(timezone.utc)
        self.stubber.add_response(
            "change_resource_record_sets",
            {
                "ChangeInfo": {
                    "Id": "FAKEID",
                    "Status": "PENDING",
                    "SubmittedAt": submitted_at,
                    "Comment": "Some comment",
                }
            },
            {
                "ChangeBatch": {
                    "Changes": [
                        {
                            "Action": "CREATE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "ResourceRecords": [{"Value": self.any()}],
                                "TTL": 60,
                                "Type": "TXT",
                            },
                        },
                    ],
                },
                "HostedZoneId": config_from_env().ROUTE53_ZONE_ID,
            },
        )
        self.stubber.add_response(
            "get_change",
            {
                "ChangeInfo": {
                    "Id": "FAKEID",
                    "Status": "INSYNC",
                    "SubmittedAt": submitted_at,
                    "Comment": "Some comment",
                }
            },
            {"Id": "FAKEID"},
        )


@pytest.fixture(autouse=True)
def route53():
    with Stubber(real_route53) as stubber:
        yield FakeRoute53(stubber)
        stubber.assert_no_pending_responses()
