import logging
import time

from sqlalchemy import and_, select, func, null
from sqlalchemy.orm import aliased

from broker.aws import alb
from broker.extensions import config, db
from broker.models import (
    DedicatedALBListener,
    DedicatedALBServiceInstance,
    Certificate,
    Operation,
)
from broker.tasks.huey import pipeline_operation

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
    if len(https_listeners) == 0:
        raise RuntimeError(
            "Could not find any HTTPS listeners. Check the app configuration."
        )
    https_listeners.sort(key=lambda x: len(x["certificates"]))
    selected_listener = https_listeners[0]
    selected_arn = selected_listener["listener_arn"]
    listener_data = alb.describe_listeners(ListenerArns=[selected_arn])
    listener_data = listener_data["Listeners"][0]
    return listener_data["LoadBalancerArn"], listener_data["ListenerArn"]


def get_potential_listeners_for_dedicated_instance(service_instance):
    # n.b. we're counting on our db count here
    # and elsewhere we rely on AWS's count.

    # Get the listeners dedicated to the org for this service (service_instance.org_id)
    active_instances = (
        select(DedicatedALBServiceInstance)
        .where(DedicatedALBServiceInstance.deactivated_at == null())
        .subquery()
    )
    instance_subquery = aliased(DedicatedALBServiceInstance, active_instances)
    query = (
        select(
            DedicatedALBListener.id,
            func.count(instance_subquery.id).label("count"),
        )
        .join_from(
            DedicatedALBListener,
            instance_subquery,
            DedicatedALBListener.listener_arn == instance_subquery.alb_listener_arn,
            isouter=True,
        )
        .where(DedicatedALBListener.dedicated_org == service_instance.org_id)
        .group_by(DedicatedALBListener.id)
        .having(func.count(instance_subquery.id) < config.MAX_CERTS_PER_ALB)
    )
    dedicated_listener_ids = db.session.execute(query).all()

    if len(dedicated_listener_ids) > 0:
        potential_listeners = [
            db.session.get(DedicatedALBListener, listener_id[0])
            for listener_id in dedicated_listener_ids
        ]
    else:
        raise RuntimeError(
            f"Could not find potential listeners for org {service_instance.org_id}"
        )

    return potential_listeners


def get_lowest_dedicated_alb(service_instance, db):
    potential_listeners = get_potential_listeners_for_dedicated_instance(
        service_instance
    )
    listener_arns = [listener.listener_arn for listener in potential_listeners]
    listener_arns.sort()  # this just makes testing easier

    alb_arn, alb_listener_arn = get_lowest_used_alb(listener_arns)
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


@pipeline_operation("Selecting load balancer")
def select_dedicated_alb(operation_id, *, operation, db, **kwargs):
    service_instance = operation.service_instance

    if (
        service_instance.alb_arn
        and operation.action == Operation.Actions.PROVISION.value
    ):
        return
    service_instance.previous_alb_listener_arn = service_instance.alb_listener_arn
    service_instance.previous_alb_arn = service_instance.alb_arn
    return get_lowest_dedicated_alb(service_instance, db)


@pipeline_operation("Selecting load balancer")
def select_alb(operation_id, *, operation, db, **kwargs):
    service_instance = operation.service_instance

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


@pipeline_operation("Adding SSL certificate to load balancer")
def add_certificate_to_alb(operation_id, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    certificate = service_instance.new_certificate

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


@pipeline_operation("Removing SSL certificate from load balancer")
def remove_certificate_from_alb(operation_id, *, operation, db, **kwargs):
    service_instance = operation.service_instance

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


@pipeline_operation("Removing SSL certificate from load balancer")
def remove_certificate_from_previous_alb(operation_id, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    remove_certificate = Certificate.query.filter(
        and_(
            Certificate.service_instance_id == service_instance.id,
            Certificate.id != service_instance.current_certificate_id,
        )
    ).first()

    if service_instance.previous_alb_listener_arn is not None:
        time.sleep(config.ALB_OVERLAP_SLEEP_TIME)
        alb.remove_listener_certificates(
            ListenerArn=service_instance.previous_alb_listener_arn,
            Certificates=[
                {"CertificateArn": remove_certificate.iam_server_certificate_arn}
            ],
        )

    _wait_for_certificate_removal(
        service_instance.previous_alb_listener_arn,
        remove_certificate.iam_server_certificate_arn,
    )

    service_instance.previous_alb_arn = None
    service_instance.previous_alb_listener_arn = None
    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Removing SSL certificate from previous load balancer")
def remove_alb_certificate_during_update_to_cdn_dedicated_waf(
    operation_id, *, operation, db, **kwargs
):
    service_instance = operation.service_instance
    remove_certificate = service_instance.alb_certificate

    if service_instance.alb_listener_arn is not None:
        time.sleep(config.ALB_OVERLAP_SLEEP_TIME)
        alb.remove_listener_certificates(
            ListenerArn=service_instance.alb_listener_arn,
            Certificates=[
                {"CertificateArn": remove_certificate.iam_server_certificate_arn}
            ],
        )

    service_instance.alb_certificate = None
    service_instance.previous_alb_arn = None
    service_instance.previous_alb_listener_arn = None
    db.session.add(service_instance)
    db.session.commit()


@pipeline_operation("Removing certificate from previous load balancer")
def remove_certificate_from_previous_alb_during_update_to_dedicated(
    operation_id, *, operation, db, **kwargs
):
    service_instance = operation.service_instance
    remove_certificate = service_instance.current_certificate

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


@pipeline_operation("Storing ALB certificate information")
def store_alb_certificate(operation_id, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    service_instance.alb_certificate = service_instance.current_certificate
    db.session.add(service_instance)
    db.session.commit()


def _wait_for_certificate_removal(listener_arn, certificate_arn):
    removed_from_alb = False
    attempts = 0
    while not removed_from_alb and attempts < config.AWS_POLL_MAX_ATTEMPTS:
        paginator = alb.get_paginator("describe_listener_certificates")
        response_iterator = paginator.paginate(
            ListenerArn=listener_arn,
        )
        certificate_arns = []
        for response in response_iterator:
            certificate_arns += [
                certificate["CertificateArn"]
                for certificate in response["Certificates"]
            ]
        removed_from_alb = certificate_arn not in certificate_arns
        attempts += 1
        time.sleep(config.AWS_POLL_WAIT_TIME_IN_SECONDS)

    if not removed_from_alb:
        raise RuntimeError(
            f"Could not verify removal of certificate {certificate_arn} from listener {listener_arn}"
        )
