import logging

import os
import sys
from openbrokerapi import api
from openbrokerapi.service_broker import (
    ServiceBroker,
    UnbindDetails,
    BindDetails,
    Binding,
    DeprovisionDetails,
    DeprovisionServiceSpec,
    ProvisionDetails,
    ProvisionedServiceSpec,
    Service,
    ServicePlan,
    ServiceMetadata,
    UnbindSpec)

logger = logging.getLogger(__name__)


class Broker(ServiceBroker):
    """
    This class should be implemented.

    The minimum setup to register a service broker requires the `catalog()`. To
    create and delete a service instance `provision` and `deprovision` are
    required. To bind and unbind a service instance you have to implement
    `bind` and `unbind` in addition.

    If some steps are async, you will have to add further methods. Please have
    a look in the Open Service Broker Spec. """

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
                    id='',
                    name='',
                    description='',
                )
            ]
        )

    def provision(self, instance_id: str, details: ProvisionDetails, async_allowed: bool, **kwargs) -> ProvisionedServiceSpec:
        pass

    def deprovision(self, instance_id: str, details: DeprovisionDetails, async_allowed: bool, **kwargs) -> DeprovisionServiceSpec:
        pass

    def bind(self, instance_id: str, binding_id: str, details: BindDetails, async_allowed: bool, **kwargs) -> Binding:
        pass

    def unbind(self, instance_id: str, binding_id: str, details: UnbindDetails, async_allowed: bool, **kwargs) -> UnbindSpec:
        pass


def create_broker_blueprint(credentials: api.BrokerCredentials):
    return api.get_blueprint(Broker(), credentials, logger)
