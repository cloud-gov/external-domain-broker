import pytest
import uuid

from botocore.exceptions import ClientError

from broker.tasks.alb import (
    get_potential_listeners_for_dedicated_instance,
    get_lowest_used_alb,
)
from tests.lib import factories


def test_gets_lowest_used_alb(alb):
    alb.expect_get_certificates_for_listener("listener-arn-0", 1)
    alb.expect_get_listeners("listener-arn-0")
    assert get_lowest_used_alb(["listener-arn-0"]) == (
        "alb-listener-arn-0",
        "listener-arn-0",
    )

    alb.expect_get_certificates_for_listener("listener-arn-0", 2)
    alb.expect_get_certificates_for_listener("listener-arn-1", 1)
    alb.expect_get_listeners("listener-arn-1")
    assert get_lowest_used_alb(["listener-arn-0", "listener-arn-1"]) == (
        "alb-listener-arn-1",
        "listener-arn-1",
    )

    alb.expect_get_certificates_for_listener("listener-arn-1", 1)
    alb.expect_get_certificates_for_listener("listener-arn-0", 2)
    alb.expect_get_listeners("listener-arn-1")
    assert get_lowest_used_alb(["listener-arn-1", "listener-arn-0"]) == (
        "alb-listener-arn-1",
        "listener-arn-1",
    )

    alb.expect_get_certificates_for_listener("listener-arn-1", 1)
    alb.expect_get_certificates_for_listener("listener-arn-2", 2)
    alb.expect_get_certificates_for_listener("listener-arn-0", 2)
    alb.expect_get_listeners("listener-arn-1")
    assert get_lowest_used_alb(
        ["listener-arn-1", "listener-arn-2", "listener-arn-0"]
    ) == ("alb-listener-arn-1", "listener-arn-1")

    alb.expect_get_certificates_for_listener("listener-arn-0", 19)
    alb.expect_get_certificates_for_listener("listener-arn-1", 0)
    alb.expect_get_certificates_for_listener("listener-arn-2", 25)
    alb.expect_get_certificates_for_listener("listener-arn-3", 20)
    alb.expect_get_certificates_for_listener("listener-arn-4", 17)
    alb.expect_get_listeners("listener-arn-1")
    assert get_lowest_used_alb(
        [
            "listener-arn-0",
            "listener-arn-1",
            "listener-arn-2",
            "listener-arn-3",
            "listener-arn-4",
        ]
    ) == ("alb-listener-arn-1", "listener-arn-1")

    alb.expect_get_certificates_for_listener("listener-arn-0", 1)
    alb.expect_get_certificates_for_listener("listener-arn-1", 1)
    alb.expect_get_certificates_for_listener("listener-arn-2", 0)
    alb.expect_get_listeners("listener-arn-2")
    assert get_lowest_used_alb(
        ["listener-arn-0", "listener-arn-1", "listener-arn-2"]
    ) == (
        "alb-listener-arn-2",
        "listener-arn-2",
    )


def test_raises_error_getting_listener_certificates(alb):
    alb.expect_get_certificates_for_listener_error("listener-arn-0")
    with pytest.raises(ClientError):
        get_lowest_used_alb(["listener-arn-0"])


def test_raises_error_on_empty_input_list_albs():
    with pytest.raises(RuntimeError):
        get_lowest_used_alb([])


def test_get_potential_listeners_with_listeners_for_instance_org(
    no_context_clean_db, no_context_app
):
    with no_context_app.app_context():
        listener = factories.DedicatedALBListenerFactory.create(
            id=100, listener_arn="listener-arn-0", dedicated_org="org-1"
        )
        service_instance = factories.DedicatedALBServiceInstanceFactory.create(
            id=str(uuid.uuid4()),
            org_id="org-1",
        )

        no_context_clean_db.session.add(listener)
        no_context_clean_db.session.add(service_instance)
        no_context_clean_db.session.commit()

        potential_listeners = get_potential_listeners_for_dedicated_instance(
            service_instance
        )
        assert potential_listeners == [listener]


def test_get_potential_listeners_no_listeners_found(
    no_context_clean_db, no_context_app
):
    with no_context_app.app_context():
        listener = factories.DedicatedALBListenerFactory.create(
            id=100, listener_arn="listener-arn-0", dedicated_org="org-1"
        )
        service_instance = factories.DedicatedALBServiceInstanceFactory.create(
            id=str(uuid.uuid4()),
            org_id="org-2",  # no listeners available for this org
        )

        no_context_clean_db.session.add(listener)
        no_context_clean_db.session.add(service_instance)
        no_context_clean_db.session.commit()

        with pytest.raises(RuntimeError):
            get_potential_listeners_for_dedicated_instance(service_instance)
