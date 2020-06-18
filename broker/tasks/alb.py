import logging

from broker.aws import alb
from broker.extensions import config
from broker.models import ALBServiceInstance, Operation
from broker.tasks import huey
from broker.tasks.db_injection import inject_db

logger = logging.getLogger(__name__)


def get_lowest_used_alb(listener_arns):
    https_listeners = []
    for listener_arn in listener_arns:
        listeners = alb.describe_listeners(ListenerArns=[listener_arn])
        https_listeners.extend(listeners["Listeners"])
    https_listeners.sort(key=lambda x: len(x["Certificates"]))
    return https_listeners[0]["LoadBalancerArn"], https_listeners[0]["ListenerArn"]


@huey.retriable_task
@inject_db
def select_alb(operation_id, **kwargs):
    db = kwargs["db"]
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    service_instance.alb_arn, service_instance.alb_listener_arn = get_lowest_used_alb(
        config.ALB_LISTENER_ARNS
    )
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
@inject_db
def add_certificate_to_alb(operation_id, **kwargs):
    db = kwargs["db"]
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    alb.add_listener_certificates(
        ListenerArn=service_instance.alb_listener_arn,
        Certificates=[
            {
                "CertificateArn": service_instance.iam_server_certificate_arn,
                "IsDefault": False,
            }
        ],
    )
    alb_config = alb.describe_load_balancers(
        LoadBalancerArns=[service_instance.alb_arn]
    )
    service_instance.domain_internal = alb_config["LoadBalancers"][0]["DNSName"]
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
@inject_db
def remove_certificate_from_alb(operation_id, **kwargs):
    db = kwargs["db"]
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    alb.remove_listener_certificates(
        ListenerArn=service_instance.alb_listener_arn,
        Certificates=[
            {
                "CertificateArn": service_instance.iam_server_certificate_arn,
                "IsDefault": False,
            }
        ],
    )
    db.session.add(service_instance)
    db.session.commit()
