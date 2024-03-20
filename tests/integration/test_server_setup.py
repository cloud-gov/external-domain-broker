import pytest

from broker.models import DedicatedALBListener
from broker.tasks.alb import load_albs


def test_server_runs(client):
    client.get("/ping")
    assert client.response.status_code == 200
    assert client.response.body == "PONG"


def test_load_albs_on_startup(clean_db):
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 0
    load_albs(["arn-1", "arn-2", "arn-3"])
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 3


def test_load_albs_on_startup_doesnt_modify_assigned_instances(clean_db):
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 0
    load_albs(["arn-1", "arn-2"])
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 2
    dedicated_listener = DedicatedALBListener.query.filter(
        DedicatedALBListener.listener_arn == "arn-1"
    ).first()
    dedicated_listener.dedicated_org = "me"
    clean_db.session.add(dedicated_listener)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    load_albs(["arn-1", "arn-2", "arn-3"])
    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 3
    dedicated_listener = DedicatedALBListener.query.filter(
        DedicatedALBListener.listener_arn == "arn-1"
    ).first()
    assert dedicated_listener.dedicated_org == "me"
