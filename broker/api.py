import logging
from typing import Optional

from openbrokerapi import errors
from openbrokerapi.service_broker import (
    BindDetails,
    Binding,
    DeprovisionDetails,
    DeprovisionServiceSpec,
    LastOperation,
    ProvisionDetails,
    ProvisionedServiceSpec,
    ProvisionState,
    Service,
    ServiceBroker,
    ServiceMetadata,
    ServicePlan,
    UnbindDetails,
    UnbindSpec,
    UpdateDetails,
    UpdateServiceSpec,
)
from sap import cf_logging


from broker import validators
from broker.extensions import config, db
from broker.lib.alb import (
    validate_migration_to_alb_params,
    update_alb_params_for_migration,
)
from broker.lib.cdn import (
    is_cdn_instance,
    provision_cdn_instance,
    update_cdn_instance,
    validate_migration_to_cdn_params,
    update_cdn_params_for_migration,
)
from broker.lib.client_error import ClientError
from broker.lib.tags import generate_instance_tags
from broker.lib.utils import (
    parse_domain_options,
    validate_domain_name_changes,
)
from broker.models import (
    Operation,
    ALBServiceInstance,
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
    DedicatedALBServiceInstance,
    MigrationServiceInstance,
    ServiceInstance,
    change_instance_type,
    ServiceInstanceTypes,
)
from broker.pipelines.alb import (
    queue_all_alb_provision_tasks_for_operation,
    queue_all_alb_deprovision_tasks_for_operation,
    queue_all_alb_update_tasks_for_operation,
)
from broker.pipelines.cdn import (
    queue_all_cdn_deprovision_tasks_for_operation,
    queue_all_cdn_provision_tasks_for_operation,
    queue_all_cdn_update_tasks_for_operation,
)
from broker.pipelines.cdn_dedicated_waf import (
    queue_all_cdn_dedicated_waf_deprovision_tasks_for_operation,
    queue_all_cdn_dedicated_waf_provision_tasks_for_operation,
    queue_all_cdn_dedicated_waf_update_tasks_for_operation,
)
from broker.pipelines.dedicated_alb import (
    queue_all_dedicated_alb_provision_tasks_for_operation,
    queue_all_dedicated_alb_update_tasks_for_operation,
)
from broker.pipelines.plan_updates import (
    queue_all_alb_to_dedicated_alb_update_tasks_for_operation,
    queue_all_cdn_to_cdn_dedicated_waf_update_tasks_for_operation,
)
from broker.pipelines.migration import (
    queue_all_cdn_broker_migration_tasks_for_operation,
    queue_all_domain_broker_migration_tasks_for_operation,
    queue_all_migration_deprovision_tasks_for_operation,
)

ALB_PLAN_ID = "6f60835c-8964-4f1f-a19a-579fb27ce694"
CDN_PLAN_ID = "1cc78b0c-c296-48f5-9182-0b38404f79ef"
MIGRATION_PLAN_ID = "739e78F5-a919-46ef-9193-1293cc086c17"
DEDICATED_ALB_PLAN_ID = "fcde69c6-077b-4edd-8d12-7b95bbc2595f"
CDN_DEDICATED_WAF_PLAN_ID = "129c8332-02ce-460a-bd6d-bde10110c654"


class API(ServiceBroker):
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def catalog(self) -> Service:
        return Service(
            id="8c16de31-104a-47b0-ba79-25e747be91d6",
            name="external-domain",
            description="Assign a custom domain to your application with TLS and an optional CDN.",
            bindable=False,
            plan_updateable=True,
            metadata=ServiceMetadata(
                displayName="AWS ALB (or CloudFront CDN) with SSL for custom domains",
                imageUrl="TODO",
                longDescription="Create a custom domain to your application with TLS and an optional CDN. This will provision a TLS certificate from Let's Encrypt, a free certificate provider.",
                providerDisplayName="Cloud.gov",
                documentationUrl="https://cloud.gov/docs/services/external-domain-service/",
                supportUrl="https://cloud.gov/support",
            ),
            plans=[
                ServicePlan(
                    id=ALB_PLAN_ID,
                    name="domain",
                    description="Basic custom domain with TLS.",
                ),
                ServicePlan(
                    id=CDN_PLAN_ID,
                    name="domain-with-cdn",
                    description="Custom domain with TLS and CloudFront.",
                ),
                ServicePlan(
                    id=MIGRATION_PLAN_ID,
                    name="migration-not-for-direct-use",
                    description="Migration plan for internal autmation.",
                    plan_updateable=True,
                ),
                ServicePlan(
                    id=DEDICATED_ALB_PLAN_ID,
                    name="domain-with-org-lb",
                    description="Basic custom domain with TLS, on org-scoped load balanacers.",
                ),
                ServicePlan(
                    id=CDN_DEDICATED_WAF_PLAN_ID,
                    name="domain-with-cdn-dedicated-waf",
                    description="Custom domain with TLS, CloudFront, and dedicated WAF.",
                ),
            ],
        )

    def last_operation(
        self, instance_id: str, operation_data: Optional[str], **kwargs
    ) -> LastOperation:
        """
        Further readings `CF Broker API#LastOperation
        <https://docs.cloudfoundry.org/services/api.html#polling>`_

        :param instance_id: Instance id provided by the platform
        :param operation_data: Operation data received from async operation
        :param kwargs: May contain additional information, improves
                       compatibility with upstream versions
        :rtype: LastOperation
        """

        instance = db.session.get(ServiceInstance, instance_id)

        if not instance:
            raise errors.ErrInstanceDoesNotExist

        if not operation_data:
            raise errors.ErrBadRequest(msg="Missing operation ID")

        operation = instance.operations.filter_by(id=int(operation_data)).first()

        if not operation:
            raise errors.ErrBadRequest(
                msg=f"Invalid operation id {operation_data} for service {instance_id}"
            )

        return LastOperation(
            state=Operation.States(operation.state),
            description=operation.step_description,
        )

    def provision(
        self, instance_id: str, details: ProvisionDetails, async_allowed: bool, **kwargs
    ) -> ProvisionedServiceSpec:
        self.logger.info("starting provision request")
        if not async_allowed:
            raise errors.ErrAsyncRequired()

        params = details.parameters or {}

        domain_names = parse_domain_options(params)
        if not domain_names:
            raise errors.ErrBadRequest("'domains' parameter required.")

        self.logger.info("validating CNAMEs")
        validators.CNAME(domain_names).validate()
        self.logger.info("validating unique domains")
        if not config.IGNORE_DUPLICATE_DOMAINS:
            validators.UniqueDomains(domain_names).validate()

        if details.plan_id == CDN_PLAN_ID:
            instance = provision_cdn_instance(instance_id, domain_names, params)
            queue = queue_all_cdn_provision_tasks_for_operation
        elif details.plan_id == CDN_DEDICATED_WAF_PLAN_ID:
            instance = provision_cdn_instance(
                instance_id,
                domain_names,
                params,
                instance_type_model=CDNDedicatedWAFServiceInstance,
            )
            queue = queue_all_cdn_dedicated_waf_provision_tasks_for_operation
        elif details.plan_id == ALB_PLAN_ID:
            instance = ALBServiceInstance(id=instance_id, domain_names=domain_names)
            queue = queue_all_alb_provision_tasks_for_operation
        elif details.plan_id == MIGRATION_PLAN_ID:
            instance = MigrationServiceInstance(
                id=instance_id, domain_names=domain_names
            )
            db.session.add(instance)
            db.session.commit()
            return ProvisionedServiceSpec(state=ProvisionState.SUCCESSFUL_CREATED)
        elif details.plan_id == DEDICATED_ALB_PLAN_ID:
            instance = DedicatedALBServiceInstance(
                id=instance_id,
                domain_names=domain_names,
                org_id=details.organization_guid,
            )
            queue = queue_all_dedicated_alb_provision_tasks_for_operation
        else:
            raise NotImplementedError()

        self.logger.info("setting origin hostname")
        self.logger.info("creating operation")

        operation = Operation(
            state=Operation.States.IN_PROGRESS.value,
            service_instance=instance,
            action=Operation.Actions.PROVISION.value,
            step_description="Queuing tasks",
        )

        self.logger.info("adding instance tags")
        catalog = self.catalog()
        tags = generate_instance_tags(instance_id, details, catalog, config.FLASK_ENV)
        instance.tags = tags

        db.session.add(instance)
        db.session.add(operation)

        self.logger.info("committing db session")
        db.session.commit()

        self.logger.info("queueing tasks")
        queue(operation.id, cf_logging.FRAMEWORK.context.get_correlation_id())
        self.logger.info("all done. Returning provisioned service spec")

        return ProvisionedServiceSpec(
            state=ProvisionState.IS_ASYNC, operation=str(operation.id)
        )

    def deprovision(
        self,
        instance_id: str,
        details: DeprovisionDetails,
        async_allowed: bool,
        **kwargs,
    ) -> DeprovisionServiceSpec:
        if not async_allowed:
            raise errors.ErrAsyncRequired()
        instance = db.session.get(ServiceInstance, instance_id)

        if not instance:
            raise errors.ErrInstanceDoesNotExist
        operation = Operation(
            state=Operation.States.IN_PROGRESS.value,
            service_instance=instance,
            action=Operation.Actions.DEPROVISION.value,
            step_description="Queuing tasks",
        )

        db.session.add(operation)
        db.session.commit()
        if details.plan_id == CDN_PLAN_ID:
            queue_all_cdn_deprovision_tasks_for_operation(
                operation.id, cf_logging.FRAMEWORK.context.get_correlation_id()
            )
        elif details.plan_id == CDN_DEDICATED_WAF_PLAN_ID:
            queue_all_cdn_dedicated_waf_deprovision_tasks_for_operation(
                operation.id, cf_logging.FRAMEWORK.context.get_correlation_id()
            )
        elif details.plan_id in (ALB_PLAN_ID, DEDICATED_ALB_PLAN_ID):
            queue_all_alb_deprovision_tasks_for_operation(
                operation.id, cf_logging.FRAMEWORK.context.get_correlation_id()
            )
        elif details.plan_id == MIGRATION_PLAN_ID:
            for o in instance.operations:
                if o.action == Operation.Actions.UPDATE.value:
                    raise errors.ErrBadRequest(
                        msg="Can't delete migration with update operations"
                    )
            queue_all_migration_deprovision_tasks_for_operation(
                operation.id, cf_logging.FRAMEWORK.context.get_correlation_id()
            )
        else:
            raise NotImplementedError()

        return DeprovisionServiceSpec(is_async=True, operation=str(operation.id))

    def update(  # noqa C901 # TODO: simplify this function
        self, instance_id: str, details: UpdateDetails, async_allowed: bool, **kwargs
    ) -> UpdateServiceSpec:
        if not async_allowed:
            raise errors.ErrAsyncRequired()

        params = details.parameters or {}

        instance = db.session.get(ServiceInstance, instance_id)

        if not instance:
            raise errors.ErrBadRequest("Service instance does not exist")

        if instance.deactivated_at:
            raise errors.ErrBadRequest(
                "Cannot update instance because it was already canceled"
            )

        if instance.has_active_operations():
            raise errors.ErrBadRequest("Instance has an active operation in progress")

        requested_domain_names = parse_domain_options(params)
        domains_to_apply = validate_domain_name_changes(
            requested_domain_names, instance
        )

        has_domain_updates = len(domains_to_apply) > 0
        if has_domain_updates:
            instance.domain_names = domains_to_apply

        if is_cdn_instance(instance) and not has_domain_updates:
            self.logger.info("domains unchanged, no need for new certificate")
            instance.new_certificate = instance.current_certificate

        noop = not has_domain_updates
        if instance.instance_type == ServiceInstanceTypes.CDN.value:
            noop = False

            if details.plan_id == CDN_PLAN_ID:
                instance = update_cdn_instance(params, instance)
                queue = queue_all_cdn_update_tasks_for_operation
            elif details.plan_id == CDN_DEDICATED_WAF_PLAN_ID:
                queue = queue_all_cdn_to_cdn_dedicated_waf_update_tasks_for_operation

                # commit any changes to the instance before changing its type,
                # which will wipe out any pending changes on `instance`
                db.session.add(instance)
                db.session.commit()

                instance = change_instance_type(
                    instance, CDNDedicatedWAFServiceInstance, db.session
                )
                instance = update_cdn_instance(params, instance)
                db.session.add(instance)
                db.session.commit()
            else:
                raise ClientError("Updating service plan is not supported")
        elif instance.instance_type == ServiceInstanceTypes.CDN_DEDICATED_WAF.value:
            noop = False

            if details.plan_id != CDN_DEDICATED_WAF_PLAN_ID:
                raise ClientError("Updating service plan is not supported")

            instance = update_cdn_instance(params, instance)

            queue = queue_all_cdn_dedicated_waf_update_tasks_for_operation
        elif instance.instance_type == ServiceInstanceTypes.ALB.value:
            if details.plan_id == ALB_PLAN_ID:
                queue = queue_all_alb_update_tasks_for_operation
            elif details.plan_id == DEDICATED_ALB_PLAN_ID:
                queue = queue_all_alb_to_dedicated_alb_update_tasks_for_operation
                instance = change_instance_type(
                    instance, DedicatedALBServiceInstance, db.session
                )
                db.session.refresh(instance)
                instance.org_id = details.context["organization_guid"]
                instance.new_certificate_id = (
                    instance.current_certificate_id
                )  # this lets us reuse renewal logic for updates
                noop = False
            else:
                raise ClientError("Updating service plan is not supported")
        elif instance.instance_type == ServiceInstanceTypes.DEDICATED_ALB.value:
            if details.plan_id != DEDICATED_ALB_PLAN_ID:
                raise ClientError("Updating service plan is not supported")
            queue = queue_all_dedicated_alb_update_tasks_for_operation
        elif instance.instance_type == ServiceInstanceTypes.MIGRATION.value:
            if details.plan_id == CDN_PLAN_ID:
                noop = False
                validate_migration_to_cdn_params(params)
                instance = change_instance_type(
                    instance, CDNServiceInstance, db.session
                )
                update_cdn_params_for_migration(instance, params)
                db.session.add(instance.current_certificate)
                queue = queue_all_cdn_broker_migration_tasks_for_operation
            elif details.plan_id == ALB_PLAN_ID:
                noop = False
                validate_migration_to_alb_params(params)
                instance = change_instance_type(
                    instance, ALBServiceInstance, db.session
                )
                update_alb_params_for_migration(instance, params)
                db.session.add(instance.current_certificate)
                queue = queue_all_domain_broker_migration_tasks_for_operation
            else:
                raise ClientError("Updating to this service plan is not supported")

        if noop:
            return UpdateServiceSpec(False)

        operation = Operation(
            state=Operation.States.IN_PROGRESS.value,
            service_instance=instance,
            action=Operation.Actions.UPDATE.value,
            step_description="Queuing tasks",
        )
        db.session.add(operation)
        db.session.add(instance)
        db.session.commit()

        queue(operation.id, cf_logging.FRAMEWORK.context.get_correlation_id())

        return UpdateServiceSpec(True, operation=str(operation.id))

    def bind(
        self,
        instance_id: str,
        binding_id: str,
        details: BindDetails,
        async_allowed: bool,
        **kwargs,
    ) -> Binding:
        pass

    def unbind(
        self,
        instance_id: str,
        binding_id: str,
        details: UnbindDetails,
        async_allowed: bool,
        **kwargs,
    ) -> UnbindSpec:
        pass
