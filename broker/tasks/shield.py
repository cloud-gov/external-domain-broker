from broker.aws import shield


class ShieldProtections:
    def __init__(self):
        self.protected_cloudfront_ids: dict[str, str] = {}

    def _list_cloudfront_protections(self):
        paginator = shield.get_paginator("list_protections")
        response_iterator = paginator.paginate(
            InclusionFilters={"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]},
        )
        for response in response_iterator:
            for protection in response["Protections"]:
                if "ResourceArn" in protection and "Id" in protection:
                    self.protected_cloudfront_ids[protection["ResourceArn"]] = (
                        protection["Id"]
                    )

    def get_cloudfront_protections(self):
        if not self.protected_cloudfront_ids:
            self._list_cloudfront_protections()
        return self.protected_cloudfront_ids
