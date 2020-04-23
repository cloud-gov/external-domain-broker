import base64
import os
import tempfile

import flask_migrate
import pytest
from flask.testing import FlaskClient
from flask.wrappers import Response
from werkzeug.datastructures import Headers

from broker import create_app


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
        auth_header = "Basic " + base64.b64encode(b":").decode("ascii")
        headers = kwargs.pop("headers", Headers())
        headers.add_header("X-Broker-Api-Version", "2.13")
        headers.add_header("Content-Type", "application/json")
        headers.add_header("Authorization", auth_header)
        kwargs["headers"] = headers

        self.response = super().open(url, *args, **kwargs)
        return self.response

    def provision_instance(self, accepts_incomplete="true"):
        self.put(
            "/v2/service_instances/1234",
            json={
                "service_id": "8c16de31-104a-47b0-ba79-25e747be91d6",
                "plan_id": "6f60835c-8964-4f1f-a19a-579fb27ce694",
                "organization_guid": "abc",
                "space_guid": "123",
            },
            query_string={"accepts_incomplete": accepts_incomplete},
        )

    def deprovision_instance(self):
        self.delete("/v2/service_instances/1234")

    def get_last_operation(self):
        self.get("/v2/service_instances/1234/last_operation",)


@pytest.yield_fixture(scope="session")
def app():
    """
    Setup our flask test app. This only gets executed once.

    Primarily stolen from
    https://github.com/nickjj/build-a-saas-app-with-flask

    :return: Flask app
    """
    _app = create_app()
    _app.config["DEBUG"] = False
    _app.config["TESTING"] = True

    # Establish an application context before running the tests.
    ctx = _app.app_context()
    ctx.push()

    yield _app

    ctx.pop()


@pytest.yield_fixture(scope="function")
def client(app):
    """
    Setup an app client. This gets executed for each test function.

    :param app: Pytest fixture
    :return: Flask app client
    """
    db_fd, app.config["DATABASE"] = tempfile.mkstemp()
    app.test_client_class = CFAPIClient
    app.response_class = CFAPIResponse
    flask_migrate.upgrade()

    yield app.test_client()

    os.close(db_fd)
    os.unlink(app.config["DATABASE"])
