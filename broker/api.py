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
from openbrokerapi.helper import to_json_response
from openbrokerapi.response import ErrorResponse
from sap import cf_logging


from broker import validators
from broker.extensions import config, db
from broker.models import (
    Operation,
    ALBServiceInstance,
    CDNServiceInstance,
    MigrationServiceInstance,
    ServiceInstance,
    change_instance_type,
    Certificate,
)
from broker.tasks.pipelines import (
    queue_all_alb_deprovision_tasks_for_operation,
    queue_all_alb_provision_tasks_for_operation,
    queue_all_alb_update_tasks_for_operation,
    queue_all_cdn_deprovision_tasks_for_operation,
    queue_all_cdn_provision_tasks_for_operation,
    queue_all_cdn_update_tasks_for_operation,
    queue_all_cdn_broker_migration_tasks_for_operation,
)

ALB_PLAN_ID = "6f60835c-8964-4f1f-a19a-579fb27ce694"
CDN_PLAN_ID = "1cc78b0c-c296-48f5-9182-0b38404f79ef"
MIGRATION_PLAN_ID = "739e78F5-a919-46ef-9193-1293cc086c17"


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
                ServicePlan(
                    id=MIGRATION_PLAN_ID,
                    name="migration-not-for-direct-use",
                    description="Migration plan for internal autmation.",
                    plan_updateable=True,
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

        domain_names = parse_domain_options(params)
        if not domain_names:
            raise errors.ErrBadRequest("'domains' parameter required.")

        self.logger.info("validating CNAMEs")
        validators.CNAME(domain_names).validate()
        self.logger.info("validating unique domains")
        validators.UniqueDomains(domain_names).validate()

        if details.plan_id == CDN_PLAN_ID:
            instance = provision_cdn_instance(instance_id, domain_names, params)
            queue = queue_all_cdn_provision_tasks_for_operation
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

        domain_names = parse_domain_options(params)
        noop = True
        if domain_names is not None:
            self.logger.info("validating CNAMEs")
            validators.CNAME(domain_names).validate()

            self.logger.info("validating unique domains")
            validators.UniqueDomains(domain_names).validate(instance)
            noop = noop and (sorted(domain_names) == sorted(instance.domain_names))
            if instance.instance_type == "cdn_service_instance" and noop:
                instance.new_certificate = instance.current_certificate
            instance.domain_names = domain_names

        if instance.instance_type == "cdn_service_instance":
            # N.B. we're using "param" in params rather than
            # params.get("param") because the OSBAPI spec
            # requires we do not mess with params that were not
            # specified, so unset and set to None have different meanings
            noop = False

            if details.plan_id != CDN_PLAN_ID:
                raise ClientError("Updating service plan is not supported")

            if "origin" in params:
                if params["origin"]:
                    origin_hostname = params["origin"]
                else:
                    origin_hostname = config.DEFAULT_CLOUDFRONT_ORIGIN
                instance.cloudfront_origin_hostname = origin_hostname

            if "path" in params:
                if params["path"]:
                    cloudfront_origin_path = params["path"]
                else:
                    cloudfront_origin_path = ""
                instance.cloudfront_origin_path = cloudfront_origin_path
            if "forward_cookies" in params:
                forward_cookie_policy, forwarded_cookies = parse_cookie_options(params)
                instance.forward_cookie_policy = forward_cookie_policy
                instance.forwarded_cookies = forwarded_cookies

            if "forward_headers" in params:
                forwarded_headers = parse_header_options(params)
            else:
                # .copy() so sqlalchemy recognizes the field has changed
                forwarded_headers = instance.forwarded_headers.copy()
            if instance.cloudfront_origin_hostname == config.DEFAULT_CLOUDFRONT_ORIGIN:
                forwarded_headers.append("HOST")
            forwarded_headers = normalize_header_list(forwarded_headers)
            instance.forwarded_headers = forwarded_headers
            if "insecure_origin" in params:
                origin_protocol_policy = "https-only"
                if params["insecure_origin"]:
                    if (
                        instance.cloudfront_origin_hostname
                        == config.DEFAULT_CLOUDFRONT_ORIGIN
                    ):
                        raise errors.ErrBadRequest(
                            "Cannot use insecure_origin with default origin"
                        )
                    origin_protocol_policy = "http-only"
                instance.origin_protocol_policy = origin_protocol_policy
            if "error_responses" in params:
                instance.error_responses = params["error_responses"]
                validators.ErrorResponseConfig(instance.error_responses).validate()

            queue = queue_all_cdn_update_tasks_for_operation
        elif instance.instance_type == "alb_service_instance":
            if details.plan_id != ALB_PLAN_ID:
                raise ClientError("Updating service plan is not supported")
            queue = queue_all_alb_update_tasks_for_operation
        elif instance.instance_type == "migration_service_instance":
            if details.plan_id == CDN_PLAN_ID:
                noop = False
                validate_migration_to_cdn_params(params)
                instance = change_instance_type(
                    instance, CDNServiceInstance, db.session
                )
                update_cdn_params_for_migration(instance, params)
                db.session.add(instance.current_certificate)
                queue = queue_all_cdn_broker_migration_tasks_for_operation
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


def parse_cookie_options(params):
    forward_cookies = params.get("forward_cookies", None)
    if forward_cookies is not None:
        forward_cookies = forward_cookies.replace(" ", "")
        if forward_cookies == "":
            forward_cookie_policy = CDNServiceInstance.ForwardCookiePolicy.NONE.value
            forwarded_cookies = []
        elif forward_cookies == "*":
            forward_cookie_policy = CDNServiceInstance.ForwardCookiePolicy.ALL.value
            forwarded_cookies = []
        else:
            forward_cookie_policy = (
                CDNServiceInstance.ForwardCookiePolicy.WHITELIST.value
            )
            forwarded_cookies = forward_cookies.split(",")
    else:
        forward_cookie_policy = CDNServiceInstance.ForwardCookiePolicy.ALL.value
        forwarded_cookies = []

    return forward_cookie_policy, forwarded_cookies


def parse_header_options(params):
    forwarded_headers = params.get("forward_headers", None)
    if forwarded_headers is None:
        forwarded_headers = []
    else:
        forwarded_headers = forwarded_headers.replace(" ", "")
        forwarded_headers = forwarded_headers.split(",")
    validators.HeaderList(forwarded_headers).validate()
    return forwarded_headers


def normalize_header_list(headers):
    headers = {header.upper() for header in headers}
    return sorted(list(headers))


def parse_domain_options(params):
    domains = params.get("domains", None)
    if isinstance(domains, str):
        domains = domains.split(",")
    if isinstance(domains, list):
        return [d.strip().lower() for d in domains]


def provision_cdn_instance(instance_id: str, domain_names: list, params: dict):
    instance = CDNServiceInstance(id=instance_id, domain_names=domain_names)
    queue = queue_all_cdn_provision_tasks_for_operation
    instance.cloudfront_origin_hostname = params.get(
        "origin", config.DEFAULT_CLOUDFRONT_ORIGIN
    )
    instance.cloudfront_origin_path = params.get("path", "")
    instance.route53_alias_hosted_zone = config.CLOUDFRONT_HOSTED_ZONE_ID
    forward_cookie_policy, forwarded_cookies = parse_cookie_options(params)
    instance.forward_cookie_policy = forward_cookie_policy
    instance.forwarded_cookies = forwarded_cookies
    forwarded_headers = parse_header_options(params)
    if instance.cloudfront_origin_hostname == config.DEFAULT_CLOUDFRONT_ORIGIN:
        forwarded_headers.append("HOST")
    forwarded_headers = normalize_header_list(forwarded_headers)

    instance.forwarded_headers = forwarded_headers
    instance.error_responses = params.get("error_responses", {})
    validators.ErrorResponseConfig(instance.error_responses).validate()
    if params.get("insecure_origin", False):
        if params.get("origin") is None:
            raise errors.ErrBadRequest(
                "'insecure_origin' cannot be set when using the default origin."
            )
        instance.origin_protocol_policy = CDNServiceInstance.ProtocolPolicy.HTTP.value
    else:
        instance.origin_protocol_policy = CDNServiceInstance.ProtocolPolicy.HTTPS.value
    return instance


def validate_migration_to_cdn_params(params):
    required = [
        "origin",
        "path",
        "forwarded_cookies",
        "forward_cookie_policy",
        "forwarded_headers",
        "insecure_origin",
        "error_responses",
        "cloudfront_distribution_id",
        "cloudfront_distribution_arn",
        "iam_server_certificate_name",
        "iam_server_certificate_id",
        "iam_server_certificate_arn",
        "domain_internal",
    ]
    for param in required:
        # since this should only be hit by another app, it seems
        # fair and smart to require all params
        if not param in params:
            raise ClientError(f"Missing parameter {param}")


def update_cdn_params_for_migration(instance, params):
    instance.cloudfront_origin_hostname = params["origin"]
    instance.cloudfront_origin_path = params["path"]
    instance.forwarded_cookies = params["forwarded_cookies"]
    instance.forward_cookie_policy = params["forward_cookie_policy"]
    if params["insecure_origin"]:
        instance.origin_protocol_policy = CDNServiceInstance.ProtocolPolicy.HTTP.value
    else:
        instance.origin_protocol_policy = CDNServiceInstance.ProtocolPolicy.HTTPS.value
    instance.forwarded_headers = params["forwarded_headers"]
    instance.error_responses = params["error_responses"]
    instance.cloudfront_distribution_id = params["cloudfront_distribution_id"]
    instance.cloudfront_distribution_arn = params["cloudfront_distribution_arn"]
    instance.domain_internal = params["domain_internal"]
    instance.current_certificate = Certificate(service_instance_id=instance.id)
    instance.current_certificate.iam_server_certificate_id = params[
        "iam_server_certificate_id"
    ]
    instance.current_certificate.iam_server_certificate_arn = params[
        "iam_server_certificate_arn"
    ]
    instance.current_certificate.iam_server_certificate_name = params[
        "iam_server_certificate_name"
    ]


class ClientError(Exception):
    """
    This class is used for errors that have messaging that clients are allowed to see.
    """

    pass
