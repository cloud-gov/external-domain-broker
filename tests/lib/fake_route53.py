from datetime import datetime, timezone

import pytest

from broker.aws import route53 as real_route53
from broker.config import config_from_env

from tests.lib.fake_aws import FakeAWS


class FakeRoute53(FakeAWS):
    def expect_create_txt_and_return_change_id(self, domain) -> str:
        now = datetime.now(timezone.utc)
        change_id = f"{domain} ID"
        self.stubber.add_response(
            "change_resource_record_sets",
            {
                "ChangeInfo": {
                    "Id": change_id,
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
                                "ResourceRecords": [{"Value": self.ANY}],
                                "TTL": 60,
                                "Type": "TXT",
                            },
                        },
                    ],
                },
                "HostedZoneId": config_from_env().ROUTE53_ZONE_ID,
            },
        )
        return change_id

    def expect_wait_for_change_insync(self, change_id: str):
        now = datetime.now(timezone.utc)
        self.stubber.add_response(
            "get_change",
            {
                "ChangeInfo": {
                    "Id": change_id,
                    "Status": "INSYNC",
                    "SubmittedAt": now,
                    "Comment": "Some comment",
                }
            },
            {"Id": change_id},
        )


@pytest.fixture(autouse=True)
def route53():
    with FakeRoute53.stubbing(real_route53) as route53_stubber:
        yield route53_stubber
