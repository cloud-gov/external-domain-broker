import boto3
import botocore

from broker.extensions import config

session = boto3.Session(region_name=config.AWS_REGION)
route53 = session.client("route53")
iam = session.client("iam")
cloudfront = session.client("cloudfront")
alb = session.client("elbv2")
