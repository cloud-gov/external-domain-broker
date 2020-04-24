import base64
import os

import flask_migrate
import pytest
from flask.testing import FlaskClient
from flask.wrappers import Response
from werkzeug.datastructures import Headers

from broker import create_app, db


class CFAPIResponse(Response):
    @property
    def body(self):
        return self.get_data(as_text=True)

    @property
    def json(self):
        return self.get_json(silent=True)


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

    def provision_instance(self, id: str, accepts_incomplete: str = "true"):
        self.put(
            f"/v2/service_instances/{id}",
            json={
                "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
                "plan_id": "6f60835c-8964-4f1f-a19a-579fb27ce694",
                "organization_guid": "abc",
                "space_guid": "123",
            },
            query_string={"accepts_incomplete": accepts_incomplete},
        )

    def deprovision_instance(self, id: str, accepts_incomplete: str = "true"):
        self.delete(
            f"/v2/service_instances/{id}",
            query_string={
                "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
                "plan_id": "6f60835c-8964-4f1f-a19a-579fb27ce694",
                "accepts_incomplete": accepts_incomplete,
            },
        )

    def get_last_operation(self, id: str, op_id: str):
        self.get(
            f"/v2/service_instances/{id}/last_operation",
            query_string={"operation": op_id},
        )


@pytest.fixture(scope="session")
def app():
    _app = create_app()

    # Establish an application context before running the tests.
    with _app.app_context():
        yield _app


@pytest.fixture(scope="function")
def client(app):
    app.test_client_class = CFAPIClient
    app.response_class = CFAPIResponse

    db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    db_path = db_uri[len("sqlite:///") :]

    if os.path.isfile(db_path):
        os.unlink(db_path)

    flask_migrate.upgrade()
    yield app.test_client()
    db.session.close()
