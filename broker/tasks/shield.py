from broker.aws import shield
from broker.tasks import huey


protected_cloudfront_resources: dict[str, str] = {}


@huey.retriable_task
def list_cloudfront_protections(operation_id: int, **kwargs):
    next_token = True
    while next_token:
        response = shield.list_protections(
            InclusionFilters={"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]}
        )
        for protection in response["Protections"]:
            protected_cloudfront_resources[protection["ResourceArn"]] = protection["Id"]
        next_token = response["NextToken"]
