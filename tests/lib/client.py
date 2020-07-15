import base64
import os

import flask_migrate
import pytest
from flask import current_app
from flask.testing import FlaskClient
from flask.wrappers import Response
from sap import cf_logging
from werkzeug.datastructures import Headers

from broker.app import create_app, db
from broker.tasks.huey import huey


class CFAPIResponse(Response):
    @property
    def body(self):
        return self.get_data(as_text=True)

    @property
    def json(self):
        return self.get_json(silent=True)


def check_last_operation_description(
    client, instance_id, operation_id, expected_message
):
    client.get_last_operation(instance_id, operation_id)
    assert "description" in client.response.json
    assert client.response.json.get("description") == expected_message


class CFAPIClient(FlaskClient):
    """
    This test client is tailored to act like the CF API.  It:

    - injects the right headers
    - adds a `response` attribute
    - uses the CFAPIResponse wrapper for all responses

    Use it like such:

        def test_server_runs(client):
            client.get("/ping")
            assert client.response.status_code == 200
            assert client.response.body() == "PONG"
    """

    def open(self, url, *args, **kwargs):
        auth_header = "Basic " + base64.b64encode(b"broker:sekrit").decode("ascii")
        headers = kwargs.pop("headers", Headers())
        headers.add_header("X-Broker-Api-Version", "2.13")
        headers.add_header("Content-Type", "application/json")
        headers.add_header("Authorization", auth_header)
        kwargs["headers"] = headers

        self.response = super().open(url, *args, **kwargs)

        return self.response

    def provision_cdn_instance(
        self, id: str, accepts_incomplete: str = "true", params: dict = None
    ):
        json = {
            "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
            "plan_id": "1cc78b0c-c296-48f5-9182-0b38404f79ef",
            "organization_guid": "abc",
            "space_guid": "123",
        }

        if params is not None:
            json["parameters"] = params

        self.put(
            f"/v2/service_instances/{id}",
            json=json,
            query_string={"accepts_incomplete": accepts_incomplete},
        )

    def deprovision_cdn_instance(self, id: str, accepts_incomplete: str = "true"):
        self.delete(
            f"/v2/service_instances/{id}",
            query_string={
                "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
                "plan_id": "1cc78b0c-c296-48f5-9182-0b38404f79ef",
                "accepts_incomplete": accepts_incomplete,
            },
        )

    def provision_alb_instance(
        self, id: str, accepts_incomplete: str = "true", params: dict = None
    ):
        json = {
            "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
            "plan_id": "6f60835c-8964-4f1f-a19a-579fb27ce694",
            "organization_guid": "abc",
            "space_guid": "123",
        }

        if params is not None:
            json["parameters"] = params

        self.put(
            f"/v2/service_instances/{id}",
            json=json,
            query_string={"accepts_incomplete": accepts_incomplete},
        )

    def deprovision_alb_instance(self, id: str, accepts_incomplete: str = "true"):
        self.delete(
            f"/v2/service_instances/{id}",
            query_string={
                "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
                "plan_id": "6f60835c-8964-4f1f-a19a-579fb27ce694",
                "accepts_incomplete": accepts_incomplete,
            },
        )

    def get_catalog(self):
        self.get("/v2/catalog")

    def get_last_operation(self, instance_id: str, op_id: str):
        self.get(
            f"/v2/service_instances/{instance_id}/last_operation",
            query_string={"operation": op_id},
        )


@pytest.fixture(scope="session")
def app():
    cf_logging._SETUP_DONE = False
    _app = create_app()

    # The Exception errorhandler seems to be firing in testing mode.
    del _app.error_handler_spec["open_broker"][None][Exception]

    with _app.app_context():
        print("Running migrations")
        db.drop_all()
        flask_migrate.upgrade()
        db.create_all()
        db.session.commit()  # Cargo Cult
        yield current_app


@pytest.fixture(scope="function")
def clean_db(app):
    """
    get a db with schema and no contents. Remove contents and restore schema when done
    Note that this pushes an app context, which can hide problems with missing contexts
    
    """
    print("Clearing Redis")
    huey.storage.conn.flushall()

    yield db
    print("Recreating tables")
    db.session.remove()
    db.drop_all()
    db.create_all()


@pytest.fixture(scope="function")
def client(clean_db, app):
    app.test_client_class = CFAPIClient
    app.response_class = CFAPIResponse

    yield app.test_client()


@pytest.fixture(scope="function")
def no_context_clean_db(no_context_app):

    with no_context_app.app_context():
        print("Running migrations")
        db.drop_all()
        flask_migrate.upgrade()
        db.create_all()
        db.session.commit()
    yield db
    with no_context_app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()


@pytest.fixture(scope="session")
def no_context_app():
    cf_logging._SETUP_DONE = False
    _app = create_app()

    # The Exception errorhandler seems to be firing in testing mode.
    del _app.error_handler_spec["open_broker"][None][Exception]
    return _app
