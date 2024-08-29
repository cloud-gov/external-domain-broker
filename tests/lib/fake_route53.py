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
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "ResourceRecords": [{"Value": self.ANY}],
                                "TTL": 60,
                                "Type": "TXT",
                            },
                        }
                    ]
                },
                "HostedZoneId": "TestZoneID",
            },
        )
        return change_id

    def expect_remove_missing_TXT(self, domain, challenge_text):
        change_id = f"{domain} ID"
        self.stubber.add_client_error(
            "change_resource_record_sets",
            "InvalidChangeBatch",
            f"Tried to delete resource record set [name='{domain}', type='A'] but it was not found",
            {
                "ChangeBatch": {
                    "Changes": [
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "ResourceRecords": [{"Value": f'"{challenge_text}"'}],
                                "TTL": 60,
                                "Type": "TXT",
                            },
                        }
                    ]
                },
                "HostedZoneId": "TestZoneID",
            },
        )

    def expect_remove_TXT(self, domain, challenge_text):
        change_id = f"{domain} ID"
        self.stubber.add_response(
            "change_resource_record_sets",
            self._change_info(change_id, "PENDING"),
            {
                "ChangeBatch": {
                    "Changes": [
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "ResourceRecords": [{"Value": f'"{challenge_text}"'}],
                                "TTL": 60,
                                "Type": "TXT",
                            },
                        }
                    ]
                },
                "HostedZoneId": "TestZoneID",
            },
        )

    def expect_create_ALIAS_and_return_change_id(
        self, domain, target, target_hosted_zone_id="Z2FDTNDATAQYW2"
    ) -> str:
        change_id = f"{domain} ID"
        self.stubber.add_response(
            "change_resource_record_sets",
            self._change_info(change_id, "PENDING"),
            {
                "ChangeBatch": {
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": "A",
                                "AliasTarget": {
                                    "DNSName": target,
                                    "HostedZoneId": target_hosted_zone_id,
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        },
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": "AAAA",
                                "AliasTarget": {
                                    "DNSName": target,
                                    "HostedZoneId": target_hosted_zone_id,
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        },
                    ]
                },
                "HostedZoneId": "TestZoneID",
            },
        )
        return change_id

    def expect_remove_ALIAS(
        self, domain, target, target_hosted_zone_id="Z2FDTNDATAQYW2"
    ):
        self.stubber.add_response(
            "change_resource_record_sets",
            self._change_info("ignored", "PENDING"),
            {
                "ChangeBatch": {
                    "Changes": [
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": "A",
                                "AliasTarget": {
                                    "DNSName": target,
                                    "HostedZoneId": target_hosted_zone_id,
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        },
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": "AAAA",
                                "AliasTarget": {
                                    "DNSName": target,
                                    "HostedZoneId": target_hosted_zone_id,
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        },
                    ]
                },
                "HostedZoneId": "TestZoneID",
            },
        )

    def expect_remove_missing_ALIAS(
        self, domain, target, target_hosted_zone_id="Z2FDTNDATAQYW2"
    ):
        self.stubber.add_client_error(
            "change_resource_record_sets",
            "InvalidChangeBatch",
            f"Tried to delete resource record set [name='{domain}', type='A'] but it was not found",
            {
                "ChangeBatch": {
                    "Changes": [
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": "A",
                                "AliasTarget": {
                                    "DNSName": target,
                                    "HostedZoneId": target_hosted_zone_id,
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        },
                        {
                            "Action": "DELETE",
                            "ResourceRecordSet": {
                                "Name": domain,
                                "Type": "AAAA",
                                "AliasTarget": {
                                    "DNSName": target,
                                    "HostedZoneId": target_hosted_zone_id,
                                    "EvaluateTargetHealth": False,
                                },
                            },
                        },
                    ]
                },
                "HostedZoneId": "TestZoneID",
            },
        )

    def expect_wait_for_change_insync(self, change_id: str):
        self.stubber.add_response(
            "get_change", self._change_info(change_id, "PENDING"), {"Id": change_id}
        )
        self.stubber.add_response(
            "get_change", self._change_info(change_id, "INSYNC"), {"Id": change_id}
        )

    def expect_create_health_check(self, service_instance_id, domain_name, idx):
        health_check_id = f"{domain_name} ID"
        self.stubber.add_response(
            "create_health_check",
            {
                "HealthCheck": {
                    "Id": health_check_id,
                    "CallerReference": f"{service_instance_id}-{idx}",
                    "HealthCheckConfig": {
                        "Type": "HTTPS",
                        "FullyQualifiedDomainName": domain_name,
                    },
                    "HealthCheckVersion": 1,
                },
                "Location": "fake-check-location",
            },
            {
                "CallerReference": f"{service_instance_id}-{idx}",
                "HealthCheckConfig": {
                    "Type": "HTTPS",
                    "FullyQualifiedDomainName": domain_name,
                },
            },
        )

    def expect_delete_health_check(self, health_check_id):
        self.stubber.add_response(
            "delete_health_check",
            {},
            {
                "HealthCheckId": health_check_id,
            },
        )

    def expect_delete_health_check_not_found(self, health_check_id: str):
        self.stubber.add_client_error(
            "delete_health_check",
            service_error_code="NoSuchHealthCheck",
            service_message="Not found",
            http_status_code=404,
            expected_params={
                "HealthCheckId": health_check_id,
            },
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

    def expect_change_tags_for_resource(self, domain_name, tags):
        health_check_id = f"{domain_name} ID"
        self.stubber.add_response(
            "change_tags_for_resource",
            {},
            {
                "ResourceType": "healthcheck",
                "ResourceId": health_check_id,
                "AddTags": tags,
            },
        )


@pytest.fixture(autouse=True)
def route53():
    with FakeRoute53.stubbing(real_route53) as route53_stubber:
        yield route53_stubber
