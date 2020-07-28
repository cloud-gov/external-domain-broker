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
from broker.models import (
    Operation,
    ALBServiceInstance,
    CDNServiceInstance,
    ServiceInstance,
)
from broker.tasks.pipelines import (
    queue_all_alb_deprovision_tasks_for_operation,
    queue_all_alb_provision_tasks_for_operation,
    queue_all_alb_update_tasks_for_operation,
    queue_all_cdn_deprovision_tasks_for_operation,
    queue_all_cdn_provision_tasks_for_operation,
    queue_all_cdn_update_tasks_for_operation,
)

ALB_PLAN_ID = "6f60835c-8964-4f1f-a19a-579fb27ce694"
CDN_PLAN_ID = "1cc78b0c-c296-48f5-9182-0b38404f79ef"


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
                    id=ALB_PLAN_ID,
                    name="domain",
                    description="Basic custom domain with TLS.",
                ),
                ServicePlan(
                    id=CDN_PLAN_ID,
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

        if params.get("domains"):
            domain_names = [d.strip().lower() for d in params["domains"].split(",")]
        else:
            raise errors.ErrBadRequest("'domains' parameter required.")

        self.logger.info("validating CNAMEs")
        validators.CNAME(domain_names).validate()
        self.logger.info("validating unique domains")
        validators.UniqueDomains(domain_names).validate()

        if details.plan_id == CDN_PLAN_ID:
            instance = CDNServiceInstance(id=instance_id, domain_names=domain_names)
            queue = queue_all_cdn_provision_tasks_for_operation
            instance.cloudfront_origin_hostname = params.get(
                "origin", config.DEFAULT_CLOUDFRONT_ORIGIN
            )
            instance.cloudfront_origin_path = params.get("path", "")
            instance.route53_alias_hosted_zone = config.CLOUDFRONT_HOSTED_ZONE_ID
            forward_cookies = params.get("forward_cookies", None)
            if forward_cookies is not None:
                forward_cookies = forward_cookies.replace(" ", "")
                if forward_cookies == "":
                    instance.forward_cookie_policy = (
                        CDNServiceInstance.ForwardCookiePolicy.NONE.value
                    )
                elif forward_cookies == "*":
                    instance.forward_cookie_policy = (
                        CDNServiceInstance.ForwardCookiePolicy.ALL.value
                    )
                else:
                    instance.forward_cookie_policy = (
                        CDNServiceInstance.ForwardCookiePolicy.WHITELIST.value
                    )
                    instance.forwarded_cookies = forward_cookies.split(",")
            forwarded_headers = params.get("forward_headers", None)
            if forwarded_headers is None:
                forwarded_headers = []
            else:
                forwarded_headers = forwarded_headers.replace(" ", "")
                forwarded_headers = forwarded_headers.split(",")
            if params.get("origin") is None:
                forwarded_headers.append("HOST")
            instance.forwarded_headers = forwarded_headers
            if params.get("insecure_origin", False):
                if params.get("origin") is None:
                    raise errors.ErrBadRequest(
                        "'insecure_origin' cannot be set when using the default origin."
                    )
                instance.origin_protocol_policy = (
                    CDNServiceInstance.ProtocolPolicy.HTTP.value
                )
            else:
                instance.origin_protocol_policy = (
                    CDNServiceInstance.ProtocolPolicy.HTTPS.value
                )
        elif details.plan_id == ALB_PLAN_ID:
            instance = ALBServiceInstance(id=instance_id, domain_names=domain_names)
            queue = queue_all_alb_provision_tasks_for_operation
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
        instance = ServiceInstance.query.get(instance_id)

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
        elif details.plan_id == ALB_PLAN_ID:
            queue_all_alb_deprovision_tasks_for_operation(
                operation.id, cf_logging.FRAMEWORK.context.get_correlation_id()
            )
        else:
            raise NotImplementedError()

        return DeprovisionServiceSpec(is_async=True, operation=str(operation.id))

    def update(
        self, instance_id: str, details: UpdateDetails, async_allowed: bool, **kwargs
    ) -> UpdateServiceSpec:
        if not async_allowed:
            raise errors.ErrAsyncRequired()

        params = details.parameters or {}

        instance = ServiceInstance.query.get(instance_id)

        if not instance:
            raise errors.ErrBadRequest("Service instance does not exist")

        if instance.deactivated_at:
            raise errors.ErrBadRequest(
                "Cannot update instance because it was already canceled"
            )

        if instance.has_active_operations():
            raise errors.ErrBadRequest("Instance has an active operation in progress")

        domain_names = [
            d.strip().lower() for d in params.get("domains", "").split(",") if len(d)
        ]
        if len(domain_names):
            self.logger.info("validating CNAMEs")
            validators.CNAME(domain_names).validate()

            self.logger.info("validating unique domains")
            validators.UniqueDomains(domain_names).validate(instance)
            instance.domain_names = domain_names

        if instance.instance_type == "cdn_service_instance":
            # N.B. we're using "param" in params rather than
            # params.get("param") because the OSBAPI spec
            # requires we do not mess with params that were not
            # specified, so unset and set to None have different meanings

            if "origin" in params:
                if params["origin"] is None:
                    instance.cloudfront_origin_hostname = (
                        config.DEFAULT_CLOUDFRONT_ORIGIN
                    )
                    # make sure HOST is in forwarded_headers. Do it by messing with params
                    # to trick the logic below into updating it.
                    params["forward_headers"] = params.get(
                        "forward_headers", []
                    ).append("HOST")
                else:
                    instance.cloudfront_origin_hostname = params["origin"]

            if "path" in params:
                if params["path"] is None:
                    instance.cloudfront_origin_path = ""
                else:
                    instance.cloudfront_origin_path = params["path"]
            if "forward_cookies" in params:
                forward_cookies = params["forward_cookies"]
                if forward_cookies is None:
                    forward_cookies = "*"

                forward_cookies = forward_cookies.replace(" ", "")
                if forward_cookies == "":
                    instance.forward_cookie_policy = (
                        CDNServiceInstance.ForwardCookiePolicy.NONE.value
                    )
                    instance.forwarded_cookies = []
                elif forward_cookies == "*":
                    instance.forward_cookie_policy = (
                        CDNServiceInstance.ForwardCookiePolicy.ALL.value
                    )
                    instance.forwarded_cookies = []
                else:
                    instance.forward_cookie_policy = (
                        CDNServiceInstance.ForwardCookiePolicy.WHITELIST.value
                    )
                    instance.forwarded_cookies = forward_cookies.split(",")

            if "forward_headers" in params:
                forwarded_headers = params["forward_headers"]
                if not forwarded_headers:
                    forwarded_headers = []
                else:
                    forwarded_headers = forwarded_headers.replace(" ", "")
                    forwarded_headers = forwarded_headers.split(",")
                if (
                    instance.cloudfront_origin_hostname
                    == config.DEFAULT_CLOUDFRONT_ORIGIN
                ):
                    forwarded_headers.append("HOST")
                instance.forwarded_headers = forwarded_headers
            if "insecure_origin" in params:
                if params["insecure_origin"]:
                    if (
                        instance.cloudfront_origin_hostname
                        == config.DEFAULT_CLOUDFRONT_ORIGIN
                    ):
                        raise errors.ErrBadRequest(
                            "Cannot use insecure_origin with default origin"
                        )
                    instance.origin_protocol_policy = "http-only"
                else:
                    instance.origin_protocol_policy = "https-only"

            queue = queue_all_cdn_update_tasks_for_operation
        else:
            queue = queue_all_alb_update_tasks_for_operation
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

        return UpdateServiceSpec(True, operation=operation.id)

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
