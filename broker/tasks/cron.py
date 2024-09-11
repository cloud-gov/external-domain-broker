import datetime
import logging

from huey import crontab
from sqlalchemy import select

from broker.extensions import db, config
from broker.lib.cdn import is_cdn_instance
from broker.models import Certificate, Operation, DedicatedALBListener, ServiceInstance
from broker.tasks import huey
from broker.pipelines.alb import (
    queue_all_alb_deprovision_tasks_for_operation,
    queue_all_alb_provision_tasks_for_operation,
    queue_all_alb_renewal_tasks_for_operation,
    queue_all_alb_update_tasks_for_operation,
)
from broker.pipelines.cdn import (
    queue_all_cdn_deprovision_tasks_for_operation,
    queue_all_cdn_provision_tasks_for_operation,
    queue_all_cdn_update_tasks_for_operation,
    queue_all_cdn_renewal_tasks_for_operation,
)
from broker.pipelines.cdn_dedicated_waf import (
    queue_all_cdn_dedicated_waf_deprovision_tasks_for_operation,
    queue_all_cdn_dedicated_waf_provision_tasks_for_operation,
    queue_all_cdn_dedicated_waf_update_tasks_for_operation,
)
from broker.pipelines.dedicated_alb import (
    queue_all_dedicated_alb_renewal_tasks_for_operation,
    queue_all_dedicated_alb_provision_tasks_for_operation,
    queue_all_dedicated_alb_update_tasks_for_operation,
)
from broker.pipelines.migration import (
    queue_all_cdn_broker_migration_tasks_for_operation,
)

logger = logging.getLogger(__name__)


def get_expiring_certs():
    certificates = (
        db.session.query(Certificate)
        .join(
            ServiceInstance,
            ServiceInstance.current_certificate_id == Certificate.id,
        )
        .filter(ServiceInstance.deactivated_at == None)
        .filter(
            Certificate.expires_at - datetime.timedelta(days=30)
            < datetime.datetime.now()
        )
        .all()
    )
    return certificates


@huey.huey.periodic_task(crontab(month="*", hour="*", day="*", minute="13"))
def scan_for_expiring_certs():
    with huey.huey.flask_app.app_context():
        logger.info("Scanning for expired certificates")
        certificates = get_expiring_certs()
        instances = [c.service_instance for c in certificates]
        cdn_renewals = []
        alb_renewals = []
        dedicated_alb_renewals = []
        for instance in instances:
            if instance.has_active_operations():
                continue
            logger.info("Instance %s needs renewal", instance.id)
            renewal = Operation(
                state=Operation.States.IN_PROGRESS.value,
                service_instance=instance,
                action=Operation.Actions.RENEW.value,
                step_description="Queuing tasks",
            )
            db.session.add(renewal)
            if is_cdn_instance(instance):
                cdn_renewals.append(renewal)
            elif instance.instance_type == "alb_service_instance":
                alb_renewals.append(renewal)
            elif instance.instance_type == "dedicated_alb_service_instance":
                dedicated_alb_renewals.append(renewal)
        db.session.commit()
        for renewal in cdn_renewals:
            queue_all_cdn_renewal_tasks_for_operation(renewal.id)
        for renewal in alb_renewals:
            queue_all_alb_renewal_tasks_for_operation(renewal.id)
        for renewal in dedicated_alb_renewals:
            queue_all_dedicated_alb_renewal_tasks_for_operation(renewal.id)

        renew_instances = cdn_renewals + alb_renewals + dedicated_alb_renewals
        # n.b. this return is only for testing - huey ignores it.
        return [instance.service_instance_id for instance in renew_instances]


@huey.huey.periodic_task(crontab(month="*", hour="*", day="*", minute="*/5"))
def restart_stalled_pipelines():
    with huey.huey.flask_app.app_context():
        for operation in scan_for_stalled_pipelines():
            reschedule_operation(operation)


@huey.huey.periodic_task(crontab(month="*", hour="*", day="*", minute="*"))
def load_albs():
    with huey.huey.flask_app.app_context():
        DedicatedALBListener.load_albs(config.DEDICATED_ALB_LISTENER_ARNS)


def scan_for_stalled_pipelines():
    logger.info("Scanning for stalled pipelines")
    fifteen_minutes_ago = datetime.datetime.now() - datetime.timedelta(minutes=15)
    operations = Operation.query.filter(
        Operation.state == Operation.States.IN_PROGRESS.value,
        Operation.updated_at <= fifteen_minutes_ago,
        Operation.canceled_at.is_(None),
    )
    return [operation.id for operation in operations]


def reschedule_operation(operation_id):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance
    logger.info(
        f"Restarting {operation.action} operation {operation.id} for service instance {service_instance.id}"
    )
    actions = Operation.Actions
    alb_queues = {
        actions.DEPROVISION.value: queue_all_alb_deprovision_tasks_for_operation,
        actions.PROVISION.value: queue_all_alb_provision_tasks_for_operation,
        actions.RENEW.value: queue_all_alb_renewal_tasks_for_operation,
        actions.UPDATE.value: queue_all_alb_update_tasks_for_operation,
    }
    cdn_queues = {
        actions.DEPROVISION.value: queue_all_cdn_deprovision_tasks_for_operation,
        actions.MIGRATE_TO_BROKER.value: queue_all_cdn_broker_migration_tasks_for_operation,
        actions.PROVISION.value: queue_all_cdn_provision_tasks_for_operation,
        actions.RENEW.value: queue_all_cdn_renewal_tasks_for_operation,
        actions.UPDATE.value: queue_all_cdn_update_tasks_for_operation,
    }
    dedicated_alb_queues = {
        actions.DEPROVISION.value: queue_all_alb_deprovision_tasks_for_operation,
        actions.PROVISION.value: queue_all_dedicated_alb_provision_tasks_for_operation,
        actions.RENEW.value: queue_all_dedicated_alb_renewal_tasks_for_operation,
        actions.UPDATE.value: queue_all_dedicated_alb_update_tasks_for_operation,
    }
    cdn_dedicated_waf_queues = {
        actions.DEPROVISION.value: queue_all_cdn_dedicated_waf_deprovision_tasks_for_operation,
        actions.PROVISION.value: queue_all_cdn_dedicated_waf_provision_tasks_for_operation,
        actions.RENEW.value: queue_all_cdn_renewal_tasks_for_operation,
        actions.UPDATE.value: queue_all_cdn_dedicated_waf_update_tasks_for_operation,
    }
    queues = {
        "cdn_service_instance": cdn_queues,
        "alb_service_instance": alb_queues,
        "dedicated_alb_service_instance": dedicated_alb_queues,
        "cdn_dedicated_waf_service_instance": cdn_dedicated_waf_queues,
    }
    queue = queues[service_instance.instance_type].get(operation.action)
    if not queue:
        raise RuntimeError(
            f"Operation {operation_id} has unknown action {operation.action}"
        )
    if operation.action == actions.RENEW.value:
        queue(operation.id)
    else:
        queue(operation.id, "Recovered operation")
