import pytest

from sqlalchemy.dialects.postgresql import insert

from broker.models import DedicatedALB, DedicatedALBListener


@pytest.fixture
def create_dedicated_alb_records(clean_db):
    stmt = insert(DedicatedALB).values(
        [
            dict(alb_arn="alb-1", dedicated_org="org-1"),
            dict(alb_arn="alb-2", dedicated_org="org-1"),
            dict(alb_arn="alb-3", dedicated_org="org-2"),
        ]
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["alb_arn"])
    clean_db.session.execute(stmt)


def test_load_alb_listeners_raises_error():
    with pytest.raises(RuntimeError):
        DedicatedALBListener.load_alb_listeners([])


def test_load_albs_on_startup(clean_db, create_dedicated_alb_records):
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 0
    DedicatedALBListener.load_alb_listeners(
        [
            ("org1", "arn-1", "alb-1"),
            ("org1", "arn-2", "alb-2"),
            ("org2", "arn-3", "alb-3"),
        ]
    )
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 3

    sorted_listeners = sorted(
        listeners,
        key=lambda listeners: listeners.listener_arn,
    )
    assert sorted_listeners[0].dedicated_org == "org1"
    assert sorted_listeners[1].dedicated_org == "org1"
    assert sorted_listeners[2].dedicated_org == "org2"


def test_load_albs_on_startup_doesnt_modify_assigned_instances(
    clean_db, create_dedicated_alb_records
):
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 0
    DedicatedALBListener.load_alb_listeners(
        [("org1", "arn-1", "alb-1"), ("org1", "arn-2", "alb-2")]
    )
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 2

    DedicatedALBListener.load_alb_listeners(
        [("org1", "arn-1", "alb-1"), ("org2", "arn-2", "alb-2")]
    )
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 2

    dedicated_listener = DedicatedALBListener.query.filter(
        DedicatedALBListener.listener_arn == "arn-2"
    ).first()
    assert dedicated_listener.dedicated_org == "org1"
