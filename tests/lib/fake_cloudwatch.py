import pytest


from broker.aws import cloudwatch_commercial as real_cloudwatch_commercial
from broker.extensions import config
from tests.lib.fake_aws import FakeAWS


class FakeCloudwatch(FakeAWS):
    def expect_put_metric_alarm(self, health_check_id: str, alarm_name: str, tags):
        request = {
            "AlarmName": alarm_name,
            "AlarmActions": [config.NOTIFICATIONS_SNS_TOPIC_ARN],
            "MetricName": "HealthCheckStatus",
            "Namespace": "AWS/Route53",
            "Statistic": "Minimum",
            "Dimensions": [
                {
                    "Name": "HealthCheckId",
                    "Value": health_check_id,
                }
            ],
            "Period": 60,
            "EvaluationPeriods": 1,
            "DatapointsToAlarm": 1,
            "Threshold": 1,
            "ComparisonOperator": "LessThanThreshold",
        }
        if tags is not None:
            request["Tags"] = tags
        self.stubber.add_response(
            "put_metric_alarm",
            {},
            request,
        )

    def expect_describe_alarms(self, alarm_name: str, expected_alarms):
        self.stubber.add_response(
            "describe_alarms",
            {"MetricAlarms": expected_alarms},
            {
                "AlarmNames": [alarm_name],
                "AlarmTypes": [
                    "MetricAlarm",
                ],
            },
        )

    def expect_delete_alarms(self, alarm_names: list[str]):
        self.stubber.add_response(
            "delete_alarms",
            {},
            {
                "AlarmNames": alarm_names,
            },
        )

    def expect_delete_alarms_not_found(self, alarm_names: list[str]):
        self.stubber.add_client_error(
            "delete_alarms",
            service_error_code="ResourceNotFound",
            service_message="Not found",
            http_status_code=404,
            expected_params={
                "AlarmNames": alarm_names,
            },
        )

    def expect_delete_alarms_unexpected_error(self, alarm_names: list[str]):
        self.stubber.add_client_error(
            "delete_alarms",
            service_error_code="RandomError",
            service_message="Unexpected error",
            http_status_code=500,
            expected_params={
                "AlarmNames": alarm_names,
            },
        )


@pytest.fixture(autouse=True)
def cloudwatch_commercial():
    with FakeCloudwatch.stubbing(real_cloudwatch_commercial) as cloudwatch_stubber:
        yield cloudwatch_stubber
