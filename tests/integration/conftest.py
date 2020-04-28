import base64
import contextlib
import os
import subprocess
import sys

import flask_migrate
import pytest
from flask import current_app
from flask.testing import FlaskClient
from flask.wrappers import Response
from werkzeug.datastructures import Headers

from broker import create_app, db


@contextlib.contextmanager
def hidden_output():
    _stderr = sys.stderr
    _stdout = sys.stdout
    null = open(os.devnull, "w")
    sys.stdout = sys.stderr = null
    try:
        yield
    finally:
        sys.stderr = _stderr
        sys.stdout = _stdout


class Tasks:
    def __init__(self):
        self.huey = current_app.huey

    def run_all_queued(self):
        __tracebackhide__ = True

        found_at_least_one_queued_task = False
        task = self.huey.dequeue()
        while task:
            found_at_least_one_queued_task = True
            task.execute()
            task = self.huey.dequeue()

        if not found_at_least_one_queued_task:
            pytest.fail("No tasks queued to run.")


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

    def get_catalog(self):
        self.get(f"/v2/catalog")

    def get_last_operation(self, instance_id: str, op_id: str):
        self.get(
            f"/v2/service_instances/{instance_id}/last_operation",
            query_string={"operation": op_id},
        )


class Pebble:
    def __init__(self):
        self._pebble_startup_string = "ACME directory available at"
        self._challtestsrv_startup_string = "Starting management server on"
        self._pebble = None
        self._challtestsrv = None

    def _wait_for_text(self, substring: str, from_process: subprocess.Popen):
        for line in from_process.stdout:
            if substring in line:
                return

    def _run(self, cmd_array):
        return subprocess.Popen(
            cmd_array,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd="/",
        )

    def start(self):
        self._pebble = self._run(
            [
                "/usr/bin/pebble",
                "-dnsserver",
                ":5053",
                "-config",
                "/test/config/pebble-config.json",
            ]
        )
        self._challtestsrv = self._run(["/usr/bin/pebble-challtestsrv"])
        self._wait_for_text(self._pebble_startup_string, from_process=self._pebble)
        self._wait_for_text(
            self._challtestsrv_startup_string, from_process=self._challtestsrv
        )

    def stop(self):
        # kill -9 and let God sort em out.
        self._challtestsrv.kill()
        self._pebble.kill()

    def is_running(self):
        if self._pebble.poll():
            return False
        if self._challtestsrv.poll():
            return False
        return True


@pytest.fixture(scope="session")
def app():
    _app = create_app()

    # The Exception errorhandler seems to be firing in testing mode.  Remove
    # it.
    del _app.error_handler_spec["open_broker"][None][Exception]
    # Establish an application context before running the tests.
    with _app.app_context():
        yield current_app


@pytest.fixture(scope="function")
def client(app, capsys):
    app.test_client_class = CFAPIClient
    app.response_class = CFAPIResponse

    db_path = app.config["SQLITE_DB_PATH"]
    if os.path.isfile(db_path):
        os.remove(app.config["SQLITE_DB_PATH"])

    with hidden_output():
        flask_migrate.upgrade()
    current_app.huey.storage.conn.flushall()

    yield app.test_client()

    db.session.close()
    if os.path.isfile(db_path):
        os.remove(app.config["SQLITE_DB_PATH"])


# This may be slow (starting/stopping procs with each test).  If so,
# we'll need to move it to a "session" fixture, and have a function
# fixture that clears data after each test.
@pytest.fixture(scope="function")
def pebble():
    pebble_client = Pebble()
    pebble_client.start()
    yield pebble_client
    pebble_client.stop()


@pytest.fixture(scope="function")
def tasks():
    return Tasks()
