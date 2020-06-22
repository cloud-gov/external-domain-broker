import logging

from broker.aws import alb
from broker.extensions import config, db
from broker.models import ALBServiceInstance, Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


def get_lowest_used_alb(listener_arns):
    https_listeners = []
    for listener_arn in listener_arns:
        listeners = alb.describe_listeners(ListenerArns=[listener_arn])
        https_listeners.extend(listeners["Listeners"])
    https_listeners.sort(key=lambda x: len(x["Certificates"]))
    return https_listeners[0]["LoadBalancerArn"], https_listeners[0]["ListenerArn"]


@huey.retriable_task
def select_alb(operation_id, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Selecting load balancer"
    db.session.add(operation)
    db.session.commit()

    service_instance.alb_arn, service_instance.alb_listener_arn = get_lowest_used_alb(
        config.ALB_LISTENER_ARNS
    )
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def add_certificate_to_alb(operation_id, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Adding SSL certificate to load balancer"
    db.session.add(operation)
    db.session.commit()

    alb.add_listener_certificates(
        ListenerArn=service_instance.alb_listener_arn,
        Certificates=[{"CertificateArn": service_instance.iam_server_certificate_arn}],
    )
    alb_config = alb.describe_load_balancers(
        LoadBalancerArns=[service_instance.alb_arn]
    )
    service_instance.domain_internal = alb_config["LoadBalancers"][0]["DNSName"]
    service_instance.route53_alias_hosted_zone = alb_config["LoadBalancers"][0][
        "CanonicalHostedZoneId"
    ]
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def remove_certificate_from_alb(operation_id, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Removing SSL certificate from load balancer"
    db.session.add(operation)
    db.session.commit()

    alb.remove_listener_certificates(
        ListenerArn=service_instance.alb_listener_arn,
        Certificates=[{"CertificateArn": service_instance.iam_server_certificate_arn}],
    )
    db.session.add(service_instance)
    db.session.commit()
