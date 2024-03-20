import pytest

from broker.models import DedicatedALBListener, DedicatedALBServiceInstance
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


def test_selects_existing_dedicated_alb(clean_db, alb, service_instance):
    our_listener_0 = DedicatedALBListener(
        listener_arn="our-arn-0", dedicated_org="our-org"
    )
    our_listener_1 = DedicatedALBListener(
        listener_arn="our-arn-1", dedicated_org="our-org"
    )
    empty_listener_0 = DedicatedALBListener(listener_arn="empty-arn-0")
    other_listener_0 = DedicatedALBListener(
        listener_arn="other-arn-0", dedicated_org="other-org"
    )
    other_listener_1 = DedicatedALBListener(
        listener_arn="other-arn-1", dedicated_org="other-org"
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
    clean_db.session.commit()

    clean_db.session.expunge_all()
    service_instance = DedicatedALBServiceInstance.query.get("4321")
    alb.expect_get_certificates_for_listener("our-arn-0", 1)
    alb.expect_get_certificates_for_listener("our-arn-1", 5)
    alb.expect_get_listeners("our-arn-0")
    get_lowest_dedicated_alb(service_instance, clean_db)
    alb.assert_no_pending_responses()
    clean_db.session.expunge_all()

    service_instance = DedicatedALBServiceInstance.query.get("4321")
    assert service_instance.alb_arn.startswith("alb-our-arn-0")


def test_selects_unassigned_alb(clean_db, alb, service_instance):
    our_listener_0 = DedicatedALBListener(listener_arn="our-arn-0")
    our_listener_1 = DedicatedALBListener(listener_arn="our-arn-1")
    other_listener_0 = DedicatedALBListener(
        listener_arn="other-arn-0", dedicated_org="other-org"
    )
    other_listener_1 = DedicatedALBListener(
        listener_arn="other-arn-1", dedicated_org="other-org"
    )

    clean_db.session.add_all(
        [our_listener_0, our_listener_1, other_listener_0, other_listener_1]
    )
    clean_db.session.commit()

    clean_db.session.expunge_all()
    service_instance = DedicatedALBServiceInstance.query.get("4321")
    alb.expect_get_certificates_for_listener("our-arn-0", 1)
    alb.expect_get_certificates_for_listener("our-arn-1", 5)
    alb.expect_get_listeners("our-arn-0")
    get_lowest_dedicated_alb(service_instance, clean_db)
    alb.assert_no_pending_responses()
    clean_db.session.expunge_all()

    listener = DedicatedALBListener.query.filter(
        DedicatedALBListener.listener_arn == "our-arn-0"
    ).first()
    service_instance = DedicatedALBServiceInstance.query.get("4321")
    assert service_instance.alb_arn.startswith("alb-our-arn-0")
    assert listener.dedicated_org == "our-org"
    assert listener.alb_arn.startswith("alb-our-arn-0")
