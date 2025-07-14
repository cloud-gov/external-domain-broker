import pytest

from broker.models import DedicatedALB
from tests.lib import factories


def test_load_albs_raises_error():
    with pytest.raises(RuntimeError):
        DedicatedALB.load_albs([])


def test_load_albs_on_startup(clean_db):
    albs = DedicatedALB.query.all()
    assert len(albs) == 0
    DedicatedALB.load_albs(
        [
            ("org1", "alb-1", "arn-1"),
            ("org1", "alb-2", "arn-2"),
            ("org2", "alb-3", "arn-3"),
        ]
    )
    albs = DedicatedALB.query.all()
    assert len(albs) == 3

    sorted_albs = sorted(
        albs,
        key=lambda albs: albs.alb_arn,
    )
    assert sorted_albs[0].alb_arn == "alb-1"
    assert sorted_albs[1].alb_arn == "alb-2"
    assert sorted_albs[2].alb_arn == "alb-3"


def test_load_albs_on_startup_doesnt_modify_assigned_org(clean_db):
    listeners = DedicatedALB.query.all()
    assert len(listeners) == 0
    DedicatedALB.load_albs(
        [
            ("org1", "alb-1", "arn-1"),
            ("org1", "alb-2", "arn-2"),
        ]
    )
    listeners = DedicatedALB.query.all()
    assert len(listeners) == 2

    DedicatedALB.load_albs(
        [
            ("org1", "alb-1", "arn-1"),
            ("org2", "alb-2", "arn-2"),
        ]
    )
    listeners = DedicatedALB.query.all()
    assert len(listeners) == 2

    dedicated_listener = DedicatedALB.query.filter(
        DedicatedALB.alb_arn == "alb-2"
    ).first()
    assert dedicated_listener.dedicated_org == "org1"


def test_load_albs_doesnt_modify_assigned_waf(clean_db):
    dedicated_alb = factories.DedicatedALBFactory.create(
        alb_arn="alb-1", dedicated_org="org1", dedicated_waf_web_acl_arn="waf-arn-1"
    )
    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    assert dedicated_alb.dedicated_waf_web_acl_arn == "waf-arn-1"

    DedicatedALB.load_albs(
        [
            ("org1", "alb-1", "arn-1"),
        ]
    )

    dedicated_alb = DedicatedALB.query.filter(DedicatedALB.alb_arn == "alb-1").first()
    assert dedicated_alb.dedicated_waf_web_acl_arn == "waf-arn-1"
