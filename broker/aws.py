import boto3
import botocore

from broker.extensions import config

commercial_session = boto3.Session(
    region_name=config.AWS_COMMERCIAL_REGION,
    aws_access_key_id=config.AWS_COMMERCIAL_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_COMMERCIAL_SECRET_ACCESS_KEY,
)
route53 = commercial_session.client("route53")
iam = commercial_session.client("iam")
cloudfront = commercial_session.client("cloudfront")
govcloud_session = boto3.Session(
    region_name=config.AWS_GOVCLOUD_REGION,
    aws_access_key_id=config.AWS_GOVCLOUD_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_GOVCLOUD_SECRET_ACCESS_KEY,
)
alb = govcloud_session.client("elbv2")
