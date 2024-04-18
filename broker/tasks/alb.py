import logging
import time

from sqlalchemy import and_, select, func, null
from sqlalchemy.orm.attributes import flag_modified


from broker.aws import alb
from broker.extensions import config, db
from broker.models import (
    DedicatedALBListener,
    DedicatedALBServiceInstance,
    Certificate,
    Operation,
)
from broker.tasks import huey

logger = logging.getLogger(__name__)


def get_lowest_used_alb(listener_arns) -> tuple[str, str]:
    # given a list of listener arns, find the listener with the least certificates associated
    # return a tuple of the load balancer arn and listener arn
    https_listeners = []
    for listener_arn in listener_arns:
        certificates = alb.describe_listener_certificates(ListenerArn=listener_arn)
        https_listeners.append(
            dict(listener_arn=listener_arn, certificates=certificates["Certificates"])
        )
    https_listeners.sort(key=lambda x: len(x["certificates"]))
    selected_listener = https_listeners[0]
    selected_arn = selected_listener["listener_arn"]
    listener_data = alb.describe_listeners(ListenerArns=[selected_arn])
    listener_data = listener_data["Listeners"][0]
    return listener_data["LoadBalancerArn"], listener_data["ListenerArn"]


def get_lowest_dedicated_alb(service_instance, db):
    # n.b. we're counting on our db count here
    # and elsewhere we rely on AWS's count.
    potential_listener_ids = db.session.execute(
        select(
            DedicatedALBListener.id,
            func.count(DedicatedALBServiceInstance.id).label("count"),
        )
        .join_from(
            DedicatedALBListener,
            DedicatedALBServiceInstance,
            DedicatedALBListener.listener_arn
            == DedicatedALBServiceInstance.alb_listener_arn,
            isouter=True,
        )
        .where(DedicatedALBListener.dedicated_org == service_instance.org_id)
        .where(DedicatedALBServiceInstance.deactivated_at == null())
        .group_by(DedicatedALBListener.id)
        .having(func.count(DedicatedALBServiceInstance.id) < 17)
    ).all()

    if potential_listener_ids:
        potential_listeners = [
            db.session.get(DedicatedALBListener, listener_id[0])
            for listener_id in potential_listener_ids
        ]
    else:
        potential_listeners = DedicatedALBListener.query.filter(
            DedicatedALBListener.dedicated_org == null()
        ).all()

    arns = [listener.listener_arn for listener in potential_listeners]
    arns.sort()  # this just makes testing easier
    alb_arn, alb_listener_arn = get_lowest_used_alb(arns)
    selected_listener = [
        listener
        for listener in potential_listeners
        if listener.listener_arn == alb_listener_arn
    ][0]
    selected_listener.alb_arn = alb_arn
    selected_listener.dedicated_org = service_instance.org_id

    service_instance.alb_arn = alb_arn
    service_instance.alb_listener_arn = alb_listener_arn

    db.session.add(service_instance)
    db.session.add(selected_listener)
    db.session.commit()


@huey.retriable_task
def select_dedicated_alb(operation_id, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Selecting load balancer"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if (
        service_instance.alb_arn
        and operation.action == Operation.Actions.PROVISION.value
    ):
        return
    service_instance.previous_alb_listener_arn = service_instance.alb_listener_arn
    service_instance.previous_alb_arn = service_instance.alb_arn
    return get_lowest_dedicated_alb(service_instance, db)


@huey.retriable_task
def select_alb(operation_id, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Selecting load balancer"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if (
        service_instance.alb_arn
        and operation.action == Operation.Actions.PROVISION.value
    ):
        return
    service_instance.previous_alb_listener_arn = service_instance.alb_listener_arn
    service_instance.previous_alb_arn = service_instance.alb_arn

    service_instance.alb_arn, service_instance.alb_listener_arn = get_lowest_used_alb(
        config.ALB_LISTENER_ARNS
    )
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def add_certificate_to_alb(operation_id, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance
    certificate = service_instance.new_certificate

    operation.step_description = "Adding SSL certificate to load balancer"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    alb.add_listener_certificates(
        ListenerArn=service_instance.alb_listener_arn,
        Certificates=[{"CertificateArn": certificate.iam_server_certificate_arn}],
    )
    alb_config = alb.describe_load_balancers(
        LoadBalancerArns=[service_instance.alb_arn]
    )
    service_instance.domain_internal = alb_config["LoadBalancers"][0]["DNSName"]
    service_instance.route53_alias_hosted_zone = alb_config["LoadBalancers"][0][
        "CanonicalHostedZoneId"
    ]
    service_instance.current_certificate = certificate
    service_instance.new_certificate = None
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def remove_certificate_from_alb(operation_id, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Removing SSL certificate from load balancer"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if service_instance.alb_listener_arn is not None:
        alb.remove_listener_certificates(
            ListenerArn=service_instance.alb_listener_arn,
            Certificates=[
                {
                    "CertificateArn": service_instance.current_certificate.iam_server_certificate_arn
                }
            ],
        )
    db.session.add(service_instance)
    db.session.commit()
    time.sleep(config.IAM_CERTIFICATE_PROPAGATION_TIME)


@huey.retriable_task
def remove_certificate_from_previous_alb(operation_id, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance
    remove_certificate = Certificate.query.filter(
        and_(
            Certificate.service_instance_id == service_instance.id,
            Certificate.id != service_instance.current_certificate_id,
        )
    ).first()

    operation.step_description = "Removing SSL certificate from load balancer"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if service_instance.previous_alb_listener_arn is not None:
        time.sleep(config.ALB_OVERLAP_SLEEP_TIME)
        alb.remove_listener_certificates(
            ListenerArn=service_instance.previous_alb_listener_arn,
            Certificates=[
                {"CertificateArn": remove_certificate.iam_server_certificate_arn}
            ],
        )

    service_instance.previous_alb_arn = None
    service_instance.previous_alb_listener_arn = None
    db.session.add(service_instance)
    db.session.commit()


@huey.retriable_task
def remove_certificate_from_previous_alb_during_update_to_dedicated(
    operation_id, **kwargs
):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance
    remove_certificate = service_instance.current_certificate

    operation.step_description = "Removing SSL certificate from load balancer"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if service_instance.previous_alb_listener_arn is not None:
        time.sleep(config.ALB_OVERLAP_SLEEP_TIME)
        alb.remove_listener_certificates(
            ListenerArn=service_instance.previous_alb_listener_arn,
            Certificates=[
                {"CertificateArn": remove_certificate.iam_server_certificate_arn}
            ],
        )

    service_instance.previous_alb_arn = None
    service_instance.previous_alb_listener_arn = None
    db.session.add(service_instance)
    db.session.commit()
