from broker.aws import shield


protected_cloudfront_ids: dict[str, str] = {}


def list_cloudfront_protections():
    if protected_cloudfront_ids:
        return protected_cloudfront_ids

    paginator = shield.get_paginator("list_protections")
    response_iterator = paginator.paginate(
        InclusionFilters={"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]},
    )
    for response in response_iterator:
        for protection in response["Protections"]:
            if "ResourceArn" in protection and "Id" in protection:
                protected_cloudfront_ids[protection["ResourceArn"]] = protection["Id"]

    return protected_cloudfront_ids
