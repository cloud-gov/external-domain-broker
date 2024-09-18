import boto3

from broker.extensions import config

commercial_session = boto3.Session(
    region_name=config.AWS_COMMERCIAL_REGION,
    aws_access_key_id=config.AWS_COMMERCIAL_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_COMMERCIAL_SECRET_ACCESS_KEY,
)
route53 = commercial_session.client("route53")
# iam for cloudfront distributions needs to be in commercial
iam_commercial = commercial_session.client("iam")
cloudfront = commercial_session.client("cloudfront")
shield = commercial_session.client("shield")

# Some services need to explicitly use the global region
commercial_global_session = boto3.Session(
    region_name=config.AWS_COMMERCIAL_GLOBAL_REGION,
    aws_access_key_id=config.AWS_COMMERCIAL_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_COMMERCIAL_SECRET_ACCESS_KEY,
)
wafv2 = commercial_global_session.client("wafv2")
cloudwatch_commercial = commercial_global_session.client("cloudwatch")
sns_commercial = commercial_global_session.client("sns")

govcloud_session = boto3.Session(
    region_name=config.AWS_GOVCLOUD_REGION,
    aws_access_key_id=config.AWS_GOVCLOUD_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_GOVCLOUD_SECRET_ACCESS_KEY,
)
alb = govcloud_session.client("elbv2")
# iam for albs needs to be govcloud
iam_govcloud = govcloud_session.client("iam")
