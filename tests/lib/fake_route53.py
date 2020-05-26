from datetime import datetime, timezone

import pytest
from botocore.stub import ANY, Stubber

from broker.aws import route53 as real_route53
from broker.config import config_from_env


class FakeRoute53:
    # How I would love to use Localstack or Moto instead.  Unfortunately,
    # neither (in the OSS free version) supports Route53 and CloudFront.  So
    # we've been reduced to using the "serviceable" `boto3.stubber`
    def __init__(self, route53_stubber):
        self.stubber = route53_stubber

    def any(self):
        return ANY

    def expect_create_txt_for(self, domain):
        now = datetime.now(timezone.utc)
        self.stubber.add_response(
            "change_resource_record_sets",
            {
                "ChangeInfo": {
                    "Id": "FAKEID",
                    "Status": "PENDING",
                    "SubmittedAt": now,
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
                    "SubmittedAt": now,
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
