import pytest  # noqa F401

from broker.extensions import db
from broker.models import Operation, MigrationServiceInstance
from tests.lib import factories
from tests.lib.client import check_last_operation_description


@pytest.fixture
def service_instance():
    service_instance = factories.MigrationServiceInstanceFactory.create(
        id="4321", domain_names=["example.com", "foo.com"]
    )
    operation = factories.OperationFactory.create(
        service_instance=service_instance,
        action=Operation.Actions.PROVISION.value,
        state=Operation.States.SUCCEEDED.value,
    )
    return service_instance


def test_refuses_to_deprovision_synchronously(client, service_instance):
    client.deprovision_migration_instance("4321", accepts_incomplete="false")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_deprovision_synchronously_by_default(client, service_instance):
    client.deprovision_migration_instance("4321", accepts_incomplete="")

    assert "AsyncRequired" in client.response.body
    assert client.response.status_code == 422


def test_refuses_to_deprovision_with_operation(client, service_instance):
    operation = factories.OperationFactory.create(
        service_instance=service_instance, action=Operation.Actions.UPDATE.value
    )

    client.deprovision_migration_instance("4321", accepts_incomplete="true")

    assert "operation" in client.response.body
    assert client.response.status_code == 400


def test_deprovision_happy_path(client, service_instance, tasks):
    subtest_deprovision_creates_deprovision_operation(client, service_instance)
    subtest_deprovision_marks_operation_as_succeeded(tasks)


def subtest_deprovision_creates_deprovision_operation(client, service_instance):
    service_instance = db.session.get(MigrationServiceInstance, "4321")
    client.deprovision_migration_instance(
        service_instance.id, accepts_incomplete="true"
    )

    assert client.response.status_code == 202, client.response.body
    assert "operation" in client.response.json

    operation_id = client.response.json["operation"]
    operation = db.session.get(Operation, operation_id)

    assert operation is not None
    assert operation.state == Operation.States.IN_PROGRESS.value
    assert operation.action == Operation.Actions.DEPROVISION.value
    assert operation.service_instance_id == service_instance.id

    return operation_id


def subtest_deprovision_marks_operation_as_succeeded(tasks):
    db.session.expunge_all()
    service_instance = db.session.get(MigrationServiceInstance, "4321")
    assert not service_instance.deactivated_at

    tasks.run_queued_tasks_and_enqueue_dependents()

    db.session.expunge_all()
    service_instance = db.session.get(MigrationServiceInstance, "4321")
    assert service_instance.deactivated_at

    assert all([o.state == "succeeded" for o in service_instance.operations])
