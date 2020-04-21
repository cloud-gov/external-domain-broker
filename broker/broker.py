import logging

from openbrokerapi import api, errors
from openbrokerapi.service_broker import (
    ServiceBroker,
    UnbindDetails,
    BindDetails,
    Binding,
    DeprovisionDetails,
    DeprovisionServiceSpec,
    ProvisionState,
    ProvisionDetails,
    ProvisionedServiceSpec,
    Service,
    ServicePlan,
    ServiceMetadata,
    UnbindSpec,
)

logger = logging.getLogger(__name__)


class Broker(ServiceBroker):
    def __init__(self):
        pass

    def catalog(self) -> Service:
        return Service(
            id="8c16de31-104a-47b0-ba79-25e747be91d6",
            name="custom-domain",
            description="Assign a custom domain to your application with TLS and an optional CDN.",
            bindable=False,
            metadata=ServiceMetadata(
                displayName="AWS ALB (or CloudFront CDN) with SSL for custom domains",
                imageUrl="TODO",
                longDescription="Create a custom domain to your application with TLS and an optional CDN. This will provision a TLS certificate from Let's Encrypt, a free certificate provider.",
                providerDisplayName="Cloud.gov",
                documentationUrl="https://github.com/cloud-gov/domain-broker",
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

    def provision(
        self, instance_id: str, details: ProvisionDetails, async_allowed: bool, **kwargs
    ) -> ProvisionedServiceSpec:
        if not async_allowed:
            raise errors.ErrAsyncRequired()
        return ProvisionedServiceSpec(state=ProvisionState.IS_ASYNC)

    def deprovision(
        self,
        instance_id: str,
        details: DeprovisionDetails,
        async_allowed: bool,
        **kwargs
    ) -> DeprovisionServiceSpec:
        pass

    def bind(
        self,
        instance_id: str,
        binding_id: str,
        details: BindDetails,
        async_allowed: bool,
        **kwargs
    ) -> Binding:
        pass

    def unbind(
        self,
        instance_id: str,
        binding_id: str,
        details: UnbindDetails,
        async_allowed: bool,
        **kwargs
    ) -> UnbindSpec:
        pass


def create_broker_blueprint(credentials: api.BrokerCredentials):
    return api.get_blueprint(Broker(), credentials, logger)
