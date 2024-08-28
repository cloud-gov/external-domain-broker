class ShieldProtections:
    def __init__(self, shield_svc):
        self.protected_cloudfront_ids: dict[str, str] = {}
        self.shield_svc = shield_svc

    def get_cloudfront_protections(self, should_refresh: bool = False):
        if not self.protected_cloudfront_ids or should_refresh:
            self._list_cloudfront_protections()
        return self.protected_cloudfront_ids

    def _list_cloudfront_protections(self):
        paginator = self.shield_svc.get_paginator("list_protections")
        response_iterator = paginator.paginate(
            InclusionFilters={"ResourceTypes": ["CLOUDFRONT_DISTRIBUTION"]},
        )
        for response in response_iterator:
            for protection in response["Protections"]:
                if "ResourceArn" in protection and "Id" in protection:
                    self.protected_cloudfront_ids[protection["ResourceArn"]] = (
                        protection["Id"]
                    )
