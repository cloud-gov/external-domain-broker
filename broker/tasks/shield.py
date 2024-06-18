from broker.aws import shield


protected_cloudfront_ids: dict[str, str] = {}


def list_cloudfront_protections():
    if protected_cloudfront_ids:
        return protected_cloudfront_ids

    next_token = True
    while next_token:
        response = shield.list_protections(
            InclusionFilters={"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]}
        )
        for protection in response["Protections"]:
            protected_cloudfront_ids[protection["ResourceArn"]] = protection["Id"]
        next_token = response["NextToken"] if "NextToken" in response else False
    return protected_cloudfront_ids
