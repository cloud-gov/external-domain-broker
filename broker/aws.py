import boto3
import botocore

config = botocore.config.Config(retries={"mode": "standard"})
session = boto3.Session()
route53 = session.client("route53", config=config)
cloudfront = session.client("cloudfront", config=config)
