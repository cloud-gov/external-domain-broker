import datetime

import pytest
from broker.extensions import db
from broker.models import Operation
from broker.tasks.cron import scan_for_stalled_pipelines, reschedule_operation
from broker.tasks.huey import huey
from sqlalchemy import text

import tests.lib.factories as factories


def test_finds_stalled_operations(clean_db):
    stalled_operation = factories.OperationFactory.create(
        id=1234, state="in progress", action="Deprovision"
    )

    unstalled = factories.OperationFactory.create(
        id=4321, state="in progress", action="Deprovision"
    )

    db.session.add(unstalled)
    db.session.add(stalled_operation)
    db.session.commit()

    ok = datetime.datetime.now() - datetime.timedelta(minutes=13)
    ok = ok.replace(tzinfo=datetime.timezone.utc)
    too_old = datetime.datetime.now() - datetime.timedelta(minutes=16)
    too_old = too_old.replace(tzinfo=datetime.timezone.utc)

    # have to do this manually to skip the onupdate on the model
    db.session.execute(
        text("UPDATE operation SET updated_at = :time WHERE id = 1234").bindparams(
            time=too_old.isoformat()
        )
    )
    db.session.execute(
        text("UPDATE operation SET updated_at = :time WHERE id = 4321").bindparams(
            time=ok.isoformat()
        )
    )
    db.session.commit()

    # sanity check - did we actually set updated_at?
    stalled_operation = db.session.get(Operation, 1234)
    assert stalled_operation.updated_at.isoformat() == too_old.isoformat()

    assert scan_for_stalled_pipelines() == [1234]


@pytest.mark.parametrize("state", ["completed", "failed"])
def test_does_not_find_ended_operations(clean_db, state):
    complete = factories.OperationFactory.create(
        id=1234, state=state, action="Deprovision"
    )

    too_old = datetime.datetime.now() - datetime.timedelta(hours=2)
    too_old = too_old.replace(tzinfo=datetime.timezone.utc)

    # have to do this manually to skip the onupdate on the model
    db.session.execute(
        text("UPDATE operation SET updated_at = :time WHERE id = 1234").bindparams(
            time=too_old.isoformat()
        )
    )
    db.session.commit()
    complete = db.session.get(Operation, 1234)

    assert scan_for_stalled_pipelines() == []


def test_does_not_find_canceled_operations(clean_db):
    complete = factories.OperationFactory.create(
        id=1234,
        state="in progress",
        action="Deprovision",
        canceled_at=datetime.datetime.now(),
    )

    too_old = datetime.datetime.now() - datetime.timedelta(hours=2)
    too_old = too_old.replace(tzinfo=datetime.timezone.utc)

    # have to do this manually to skip the onupdate on the model
    db.session.execute(
        text("UPDATE operation SET updated_at = :time WHERE id = 1234").bindparams(
            time=too_old.isoformat()
        )
    )
    db.session.commit()
    complete = db.session.get(Operation, 1234)

    assert scan_for_stalled_pipelines() == []


@pytest.mark.parametrize(
    "action", ["Provision", "Deprovision", "Renew", "Update", "Migrate to broker"]
)
def test_reschedules_operation(clean_db, action):
    stalled_operation = factories.OperationFactory.create(
        id=1234, state="in progress", action=action
    )
    db.session.add(stalled_operation)
    db.session.commit()
    stalled_operation = db.session.get(Operation, 1234)

    reschedule_operation(1234)
    assert len(huey.pending()) == 1
    huey.dequeue()
