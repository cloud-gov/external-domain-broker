import pytest
import datetime

from broker.tasks.cron import reschedule_operation, scan_for_stalled_pipelines

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


@pytest.fixture
def stalled_service_instance(
    clean_db, operation_id, service_instance_id, instance_factory
):
    service_instance = instance_factory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
    )
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()
    fifteen_minutes_ago = datetime.datetime.now() - datetime.timedelta(minutes=15)
    OperationFactory.create(
        id=operation_id,
        service_instance=service_instance,
        updated_at=fifteen_minutes_ago,
    )
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


@pytest.mark.parametrize(
    "instance_factory",
    [
        ALBServiceInstanceFactory,
        CDNServiceInstanceFactory,
        CDNDedicatedWAFServiceInstanceFactory,
        DedicatedALBServiceInstanceFactory,
    ],
)
def test_scan_for_stalled_pipelines(stalled_service_instance, operation_id):
    # assert no error is thrown
    operation_ids = scan_for_stalled_pipelines()
    assert operation_ids == [int(operation_id)]
