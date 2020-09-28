import datetime
import logging

from huey import crontab

from broker.extensions import config, db
from broker.models import Certificate, ServiceInstance, Operation
from broker.tasks import huey
from broker.tasks.pipelines import (
    queue_all_alb_deprovision_tasks_for_operation,
    queue_all_alb_provision_tasks_for_operation,
    queue_all_alb_renewal_tasks_for_operation,
    queue_all_alb_update_tasks_for_operation,
    queue_all_cdn_deprovision_tasks_for_operation,
    queue_all_cdn_broker_migration_tasks_for_operation,
    queue_all_cdn_provision_tasks_for_operation,
    queue_all_cdn_update_tasks_for_operation,
    queue_all_cdn_renewal_tasks_for_operation,
)

logger = logging.getLogger(__name__)


@huey.huey.periodic_task(crontab(month="*", hour="*", day="*", minute="13"))
def scan_for_expiring_certs():
    if not config.RUN_CRON:
        return
    with huey.huey.flask_app.app_context():
        logger.info("Scanning for expired certificates")
        # TODO: skip SIs with active operations
        certificates = Certificate.query.filter(
            Certificate.expires_at - datetime.timedelta(days=30)
            < datetime.datetime.now()
        ).all()
        instances = [
            c.service_instance
            for c in certificates
            if not c.service_instance.deactivated_at
            and not c.service_instance.has_active_operations()
        ]
        cdn_renewals = []
        alb_renewals = []
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
            if instance.instance_type == "cdn_service_instance":
                cdn_renewals.append(renewal)
            else:
                alb_renewals.append(renewal)
        db.session.commit()
        for renewal in cdn_renewals:
            queue_all_cdn_renewal_tasks_for_operation(renewal.id)
        for renewal in alb_renewals:
            queue_all_alb_renewal_tasks_for_operation(renewal.id)

        renew_instances = cdn_renewals + alb_renewals
        # n.b. this return is only for testing - huey ignores it.
        return [instance.service_instance_id for instance in renew_instances]


@huey.huey.periodic_task(crontab(month="*", hour="*", day="*", minute="*/5"))
def restart_stalled_pipelines():
    if not config.RUN_CRON:
        return
    with huey.huey.flask_app.app_context():
        for operation in scan_for_stalled_pipelines():
            reschedule_operation(operation)


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
    operation = Operation.query.get(operation_id)
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
    queues = {"cdn_service_instance": cdn_queues, "alb_service_instance": alb_queues}
    queue = queues[service_instance.instance_type].get(operation.action)
    if not queue:
        raise RuntimeError(
            f"Operation {operation_id} has unknown action {operation.action}"
        )
    queue(operation.id, "Recovered operation")
