import boto3
import botocore

session = boto3.Session()
route53 = session.client("route53")
iam = session.client("iam")
cloudfront = session.client("cloudfront")
