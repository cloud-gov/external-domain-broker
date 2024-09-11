import pytest

from broker.models import ServiceInstanceTypes
from broker.tasks.cron import reschedule_operation

from tests.lib.factories import (
    ALBServiceInstanceFactory,
    CDNServiceInstanceFactory,
    CDNDedicatedWAFServiceInstanceFactory,
    DedicatedALBServiceInstanceFactory,
    OperationFactory,
)


@pytest.fixture
def service_instance(clean_db, operation_id, service_instance_id, instance_factory):
    service_instance = instance_factory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
    )
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()
    OperationFactory.create(id=operation_id, service_instance=service_instance)
    return service_instance


@pytest.mark.parametrize(
    "instance_factory",
    [
        ALBServiceInstanceFactory,
        CDNServiceInstanceFactory,
        CDNDedicatedWAFServiceInstanceFactory,
        DedicatedALBServiceInstanceFactory,
    ],
)
def test_reschedule_operation_for_all_instance_types(service_instance, operation_id):
    result = reschedule_operation(operation_id)
    assert result is not None
