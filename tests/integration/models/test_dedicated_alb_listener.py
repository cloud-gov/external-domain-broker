from broker.models import DedicatedALBListener


def test_load_albs_on_startup(clean_db):
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 0
    DedicatedALBListener.load_albs({"arn-1": "org1", "arn-2": "org1", "arn-3": "org2"})
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 3


def test_load_albs_on_startup_doesnt_modify_assigned_instances(clean_db):
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 0
    DedicatedALBListener.load_albs({"arn-1": "org1", "arn-2": "org1"})
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 2

    DedicatedALBListener.load_albs({"arn-1": "org1", "arn-2": "org2"})
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 2
    dedicated_listener = DedicatedALBListener.query.filter(
        DedicatedALBListener.listener_arn == "arn-2"
    ).first()
    assert dedicated_listener.dedicated_org == "org1"
