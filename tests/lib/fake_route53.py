from datetime import datetime, timezone

import pytest

from broker.aws import route53 as real_route53

from tests.lib.fake_aws import FakeAWS


class FakeRoute53(FakeAWS):
    def expect_create_TXT_and_return_change_id(self, domain) -> str:
        change_id = f"{domain} ID"
        self.stubber.add_response(
            "change_resource_record_sets",
            self._change_info(change_id, "PENDING"),
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
                "HostedZoneId": "TestZoneID",
            },
        )
        return change_id

    def expect_create_ALIAS_and_return_change_id(self, domain, target) -> str:
        change_id = f"{domain} ID"
        self.stubber.add_response(
            "change_resource_record_sets",
            self._change_info(change_id, "PENDING"),
            {
                "ChangeBatch": {
                    "Changes": [
                        {
                            "Action": "CREATE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": "A",
                                "AliasTarget": {
                                    "DNSName": target,
                                    "HostedZoneId": "Z2FDTNDATAQYW2",
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        },
                    ],
                },
                "HostedZoneId": "TestZoneID",
            },
        )
        return change_id

    def expect_wait_for_change_insync(self, change_id: str):
        self.stubber.add_response(
            "get_change", self._change_info(change_id, "PENDING"), {"Id": change_id},
        )
        self.stubber.add_response(
            "get_change", self._change_info(change_id, "INSYNC"), {"Id": change_id},
        )

    def _change_info(self, change_id: str, status: str = "PENDING"):
        now = datetime.now(timezone.utc)
        return {
            "ChangeInfo": {
                "Id": change_id,
                "Status": status,
                "SubmittedAt": now,
                "Comment": "Some comment",
            }
        }


@pytest.fixture(autouse=True)
def route53():
    with FakeRoute53.stubbing(real_route53) as route53_stubber:
        yield route53_stubber
