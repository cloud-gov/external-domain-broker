import pytest
import base64

from broker import create_app
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers
from flask.wrappers import Response


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
        print(headers)
        kwargs["headers"] = headers

        self.response = super().open(url, *args, **kwargs)
        return self.response


@pytest.yield_fixture(scope="session")
def app():
    """
    Setup our flask test app, this only gets executed once.

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
    Setup an app client, this gets executed for each test function.

    :param app: Pytest fixture
    :return: Flask app client
    """
    app.test_client_class = CFAPIClient
    app.response_class = CFAPIResponse
    yield app.test_client()
