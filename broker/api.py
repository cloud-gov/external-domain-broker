import logging
import sys
from typing import Optional

from sap import cf_logging

from openbrokerapi import errors
from openbrokerapi.service_broker import (
    BindDetails,
    Binding,
    DeprovisionDetails,
    DeprovisionServiceSpec,
    LastOperation,
    OperationState,
    ProvisionDetails,
    ProvisionedServiceSpec,
    ProvisionState,
    Service,
    ServiceBroker,
    ServiceMetadata,
    ServicePlan,
    UnbindDetails,
    UnbindSpec,
)

from broker.extensions import db, config
from broker.models import Operation, ServiceInstance
from broker import validators
from broker.tasks import (
    queue_all_provision_tasks_for_operation,
    queue_all_deprovision_tasks_for_operation,
)


class API(ServiceBroker):
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def catalog(self) -> Service:
        return Service(
            id="8c16de31-104a-47b0-ba79-25e747be91d6",
            name="external-domain",
            description="Assign a custom domain to your application with TLS and an optional CDN.",
            bindable=False,
            metadata=ServiceMetadata(
                displayName="AWS ALB (or CloudFront CDN) with SSL for custom domains",
                imageUrl="TODO",
                longDescription="Create a custom domain to your application with TLS and an optional CDN. This will provision a TLS certificate from Let's Encrypt, a free certificate provider.",
                providerDisplayName="Cloud.gov",
                documentationUrl="https://github.com/cloud-gov/external-domain-broker",
                supportUrl="https://cloud.gov/support",
            ),
            plans=[
                ServicePlan(
                    id="6f60835c-8964-4f1f-a19a-579fb27ce694",
                    name="domain",
                    description="Basic custom domain with TLS.",
                ),
                ServicePlan(
                    id="1cc78b0c-c296-48f5-9182-0b38404f79ef",
                    name="domain-with-cdn",
                    description="Custom domain with TLS and CloudFront.",
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

        instance = ServiceInstance.query.get(instance_id)

        if not instance:
            raise errors.ErrInstanceDoesNotExist

        if not operation_data:
            raise errors.ErrBadRequest(msg="Missing operation ID")

        operation = instance.operations.filter_by(id=int(operation_data)).first()

        if not operation:
            raise errors.ErrBadRequest(
                msg=f"Invalid operation id {operation_data} for service {instance_id}"
            )

        return LastOperation(state=operation.state)

    def provision(
        self, instance_id: str, details: ProvisionDetails, async_allowed: bool, **kwargs
    ) -> ProvisionedServiceSpec:
        if not async_allowed:
            raise errors.ErrAsyncRequired()

        params = details.parameters or {}

        if params.get("domains"):
            domain_names = [d.strip().lower() for d in params["domains"].split(",")]
        else:
            raise errors.ErrBadRequest("'domains' parameter required.")

        validators.CNAME(domain_names).validate()
        validators.UniqueDomains(domain_names).validate()

        instance = ServiceInstance(id=instance_id, domain_names=domain_names)

        instance.cloudfront_origin_hostname = params.get(
            "origin", config.DEFAULT_CLOUDFRONT_ORIGIN
        )
        instance.cloudfront_origin_path = params.get("path", "")

        operation = Operation(
            state=OperationState.IN_PROGRESS,
            service_instance=instance,
            action=Operation.Actions.PROVISION,
        )

        db.session.add(instance)
        db.session.add(operation)
        db.session.commit()
        queue_all_provision_tasks_for_operation(operation.id, cf_logging.FRAMEWORK.context.get_correlation_id())

        return ProvisionedServiceSpec(
            state=ProvisionState.IS_ASYNC, operation=operation.id
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
        instance = ServiceInstance.query.get(instance_id)

        if not instance:
            raise errors.ErrInstanceDoesNotExist
        operation = Operation(
            state=OperationState.IN_PROGRESS,
            service_instance=instance,
            action=Operation.Actions.DEPROVISION,
        )

        db.session.add(operation)
        db.session.commit()
        queue_all_deprovision_tasks_for_operation(operation.id)

        return DeprovisionServiceSpec(is_async=True, operation=operation.id)

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
