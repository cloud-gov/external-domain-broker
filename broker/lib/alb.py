from broker.lib.client_error import ClientError
from broker.models import Certificate


def validate_migration_to_alb_params(params):
    required = [
        "iam_server_certificate_name",
        "iam_server_certificate_id",
        "iam_server_certificate_arn",
        "domain_internal",
        "alb_arn",
        "alb_listener_arn",
        "hosted_zone_id",
    ]
    for param in required:
        # since this should only be hit by another app, it seems
        # fair and smart to require all params
        if param not in params:
            raise ClientError(f"Missing parameter {param}")


def update_alb_params_for_migration(instance, params):
    instance.current_certificate = Certificate(service_instance_id=instance.id)
    instance.current_certificate.iam_server_certificate_id = params[
        "iam_server_certificate_id"
    ]
    instance.current_certificate.iam_server_certificate_arn = params[
        "iam_server_certificate_arn"
    ]
    instance.current_certificate.iam_server_certificate_name = params[
        "iam_server_certificate_name"
    ]
    instance.domain_internal = params["domain_internal"]
    instance.route53_alias_hosted_zone = params["hosted_zone_id"]
    instance.alb_listener_arn = params["alb_listener_arn"]
    instance.alb_arn = params["alb_arn"]
