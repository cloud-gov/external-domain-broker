import datetime

import pytest

from broker.models import (
    DedicatedALB,
    DedicatedALBListener,
    DedicatedALBServiceInstance,
)
from broker.tasks.alb import get_lowest_dedicated_alb


from tests.lib import factories


@pytest.fixture
def service_instance(clean_db):
    service_instance = factories.DedicatedALBServiceInstanceFactory.create(
        id="4321",
        domain_names=["example.com", "foo.com"],
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        alb_arn="our-arn-1",
        alb_listener_arn="alb-our-arn-1",
        domain_internal="fake1234.cloud.test",
        org_id="our-org",
    )
    return service_instance


def test_selects_existing_dedicated_alb(clean_db, alb, service_instance):
    alb_0 = DedicatedALB(
        alb_arn="alb-our-arn-0",
        dedicated_org="our-org",
    )
    alb_1 = DedicatedALB(
        alb_arn="alb-our-arn-1",
        dedicated_org="our-org",
    )
    alb_2 = DedicatedALB(
        alb_arn="alb-our-arn-2",
        dedicated_org="another-org",
    )
    alb_3 = DedicatedALB(
        alb_arn="alb-our-arn-3",
        dedicated_org="other-org",
    )
    alb_4 = DedicatedALB(
        alb_arn="alb-our-arn-4",
        dedicated_org="other-org",
    )
    clean_db.session.add_all(
        [
            alb_0,
            alb_1,
            alb_2,
            alb_3,
            alb_4,
        ]
    )
    clean_db.session.commit()

    our_listener_0 = DedicatedALBListener(
        listener_arn="our-arn-0",
        dedicated_org="our-org",
        alb_arn="alb-our-arn-0",
    )
    our_listener_1 = DedicatedALBListener(
        listener_arn="our-arn-1",
        dedicated_org="our-org",
        alb_arn="alb-our-arn-1",
    )
    empty_listener_0 = DedicatedALBListener(
        listener_arn="empty-arn-0",
        dedicated_org="another-org",
        alb_arn="alb-our-arn-2",
    )
    other_listener_0 = DedicatedALBListener(
        listener_arn="other-arn-0",
        dedicated_org="other-org",
        alb_arn="alb-our-arn-3",
    )
    other_listener_1 = DedicatedALBListener(
        listener_arn="other-arn-1",
        dedicated_org="other-org",
        alb_arn="alb-our-arn-4",
    )

    clean_db.session.add_all(
        [
            our_listener_0,
            our_listener_1,
            empty_listener_0,
            other_listener_0,
            other_listener_1,
        ]
    )
    for i in range(16):
        instance = factories.DedicatedALBServiceInstanceFactory.create(
            domain_names=[f"random{i}.example.com"], alb_listener_arn="our-arn-0"
        )
    for i in range(17):
        instance = factories.DedicatedALBServiceInstanceFactory.create(
            domain_names=[f"random{i}.example.com"], alb_listener_arn="our-arn-1"
        )
        clean_db.session.add(instance)
    clean_db.session.commit()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(DedicatedALBServiceInstance, "4321")
    alb.expect_get_certificates_for_listener("our-arn-0", 16)
    alb.expect_get_certificates_for_listener("our-arn-1", 17)
    alb.expect_get_listeners("our-arn-0", "alb-our-arn-0")
    get_lowest_dedicated_alb(service_instance, clean_db)
    alb.assert_no_pending_responses()
    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.alb_arn.startswith("alb-our-arn-0")


def test_adds_new_alb_when_assigned_is_near_full(clean_db, alb, service_instance):
    alb_0 = DedicatedALB(
        alb_arn="alb-our-arn-0",
        dedicated_org="our-org",
    )
    alb_1 = DedicatedALB(
        alb_arn="alb-our-arn-1",
        dedicated_org="our-org",
    )
    alb_2 = DedicatedALB(
        alb_arn="alb-our-arn-2",
        dedicated_org="other-org",
    )
    alb_3 = DedicatedALB(
        alb_arn="alb-our-arn-3",
        dedicated_org="other-org",
    )
    clean_db.session.add_all(
        [
            alb_0,
            alb_1,
            alb_2,
            alb_3,
        ]
    )
    clean_db.session.commit()

    our_listener_0 = DedicatedALBListener(
        listener_arn="our-arn-0",
        dedicated_org="our-org",
        alb_arn="alb-our-arn-0",
    )
    available_listener_0 = DedicatedALBListener(
        listener_arn="available-arn-0",
        dedicated_org="our-org",
        alb_arn="alb-our-arn-1",
    )
    other_listener_0 = DedicatedALBListener(
        listener_arn="other-arn-0",
        dedicated_org="other-org",
        alb_arn="alb-our-arn-2",
    )
    other_listener_1 = DedicatedALBListener(
        listener_arn="other-arn-1",
        dedicated_org="other-org",
        alb_arn="alb-our-arn-3",
    )

    clean_db.session.add_all(
        [our_listener_0, available_listener_0, other_listener_0, other_listener_1]
    )
    clean_db.session.commit()
    for i in range(19):
        instance = factories.DedicatedALBServiceInstanceFactory.create(
            domain_names=[f"random{i}.example.com"], alb_listener_arn="our-arn-0"
        )
        clean_db.session.add(instance)
    clean_db.session.commit()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(DedicatedALBServiceInstance, "4321")
    alb.expect_get_certificates_for_listener("available-arn-0", 0)
    alb.expect_get_listeners("available-arn-0", "alb-our-arn-1")
    get_lowest_dedicated_alb(service_instance, clean_db)
    alb.assert_no_pending_responses()
    clean_db.session.expunge_all()

    listener = DedicatedALBListener.query.filter(
        DedicatedALBListener.listener_arn == "available-arn-0"
    ).first()
    service_instance = clean_db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.alb_arn.startswith("alb-our-arn-1")
    assert listener.dedicated_org == "our-org"
    assert listener.alb_arn.startswith("alb-our-arn-1")


def test_selects_existing_dedicated_alb_when_it_has_deactivated_instances(
    clean_db, alb, service_instance
):
    alb_0 = DedicatedALB(
        alb_arn="alb-our-arn-0",
        dedicated_org="our-org",
    )
    clean_db.session.add(alb_0)
    clean_db.session.commit()

    # this tests a bug where the filter clause on our join caused the query not to return listeners with only deactivated instances
    our_listener_0 = DedicatedALBListener(
        listener_arn="our-arn-0", dedicated_org="our-org", alb_arn="alb-our-arn-0"
    )

    clean_db.session.add(our_listener_0)
    instance = factories.DedicatedALBServiceInstanceFactory.create(
        domain_names=[f"random.example.com"],
        alb_listener_arn="our-arn-0",
        deactivated_at=datetime.datetime.now(),
    )
    clean_db.session.add(instance)
    clean_db.session.commit()

    clean_db.session.expunge_all()
    service_instance = clean_db.session.get(DedicatedALBServiceInstance, "4321")
    alb.expect_get_certificates_for_listener("our-arn-0", 0)
    alb.expect_get_listeners("our-arn-0", "alb-our-arn-0")
    get_lowest_dedicated_alb(service_instance, clean_db)
    alb.assert_no_pending_responses()
    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(DedicatedALBServiceInstance, "4321")
    assert service_instance.alb_arn.startswith("alb-our-arn-0")
