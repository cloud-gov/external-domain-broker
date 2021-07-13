"""
These tests are about updating from one plan type to another
"""
from broker.extensions import config, db
from broker.models import (
    Challenge,
    Operation,
    CDNServiceInstance,
    ALBServiceInstance,
    ServiceInstance,
    change_instance_type,
    MigrationServiceInstance,
)
import pytest

from tests.lib import factories


@pytest.fixture
def alb_instance(clean_db):
    service_instance = factories.ALBServiceInstanceFactory.create(
        id="started-as-alb-instance", domain_names=["example.com", "foo.com"]
    )
    return service_instance


@pytest.fixture
def migration_instance(clean_db):
    service_instance = factories.MigrationServiceInstanceFactory.create(
        id="started-as-migration-instance", domain_names=["example.com", "foo.com"]
    )
    return service_instance


@pytest.fixture
def cdn_instance(clean_db):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="started-as-cdn-instance",
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
    )
    return service_instance


def test_refuses_if_new_type_not_serviceinstance(cdn_instance):
    with pytest.raises(NotImplementedError):
        change_instance_type(cdn_instance, Challenge, None)
    with pytest.raises(NotImplementedError):
        change_instance_type(cdn_instance, ServiceInstance, None)


def test_refuses_if_not_serviceinstance():
    with pytest.raises(NotImplementedError):
        change_instance_type(Challenge(), ALBServiceInstance, None)


def test_returns_instance_if_same_type(cdn_instance):
    instance = change_instance_type(cdn_instance, CDNServiceInstance, None)
    assert instance is cdn_instance


def test_refuses_not_yet_implemented_transformations(
    cdn_instance, migration_instance, alb_instance
):
    with pytest.raises(NotImplementedError):
        change_instance_type(cdn_instance, ALBServiceInstance, None)
    with pytest.raises(NotImplementedError):
        change_instance_type(cdn_instance, MigrationServiceInstance, None)
    with pytest.raises(NotImplementedError):
        change_instance_type(alb_instance, CDNServiceInstance, None)
    with pytest.raises(NotImplementedError):
        change_instance_type(alb_instance, MigrationServiceInstance, None)


def test_migration_to_cdn(migration_instance, clean_db):
    instance = change_instance_type(
        migration_instance, CDNServiceInstance, clean_db.session
    )
    clean_db.session.expunge_all()
    instance = CDNServiceInstance.query.get("started-as-migration-instance")
    assert instance is not None
    assert instance.domain_names == ["example.com", "foo.com"]
