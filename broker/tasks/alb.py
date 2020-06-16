import logging

from broker.aws import alb
from broker.extensions import config
from broker.models import ALBServiceInstance, Operation
from broker.tasks import huey
from broker.tasks.db_injection import inject_db

logger = logging.getLogger(__name__)


@huey.retriable_task
@inject_db
def select_alb_and_upload_certificate(operation_id, **kwargs):
    db = kwargs["db"]
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    service_instance.alb_arn = config.ALB_ARNS[0]
    listeners = alb.describe_listeners(LoadBalancerArn=service_instance.alb_arn)
    https_listener = [
        listener
        for listener in listeners["Listeners"]
        if listener["Protocol"] == "HTTPS"
    ][0]
    alb.add_listener_certificates(
        ListenerArn=https_listener["ListenerArn"],
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
