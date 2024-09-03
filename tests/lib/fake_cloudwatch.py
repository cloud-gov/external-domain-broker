import pytest


from broker.aws import cloudwatch_commercial as real_cloudwatch_commercial
from broker.extensions import config
from tests.lib.fake_aws import FakeAWS


class FakeCloudwatch(FakeAWS):
    def expect_put_metric_alarm(self, health_check_id: str, alarm_name: str, tags):

        self.stubber.add_response(
            "put_metric_alarm",
            {},
            {
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
                "Tags": tags,
            },
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


@pytest.fixture(autouse=True)
def cloudwatch_commercial():
    with FakeCloudwatch.stubbing(real_cloudwatch_commercial) as cloudwatch_stubber:
        yield cloudwatch_stubber
