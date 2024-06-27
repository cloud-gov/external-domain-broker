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

    # response = shield.list_protections(
    #     InclusionFilters={"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]},
    # )

    # while True:
    #     for protection in response["Protections"]:
    #         if "ResourceArn" in protection and "Id" in protection:
    #             protected_cloudfront_ids[protection["ResourceArn"]] = protection["Id"]

    #     next_token = response["NextToken"] if "NextToken" in response else ""
    #     if not next_token:
    #         break

    #     response = shield.list_protections(
    #         InclusionFilters={"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]},
    #         NextToken=next_token,
    #     )

    return protected_cloudfront_ids
