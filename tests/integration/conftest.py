import base64
import contextlib
import os
import sys
import requests

import flask_migrate
import pytest
from flask import current_app
from flask.testing import FlaskClient
from flask.wrappers import Response
from werkzeug.datastructures import Headers
from dataclasses import dataclass, asdict

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

    def run_pipeline_stages(self, num_pipeline_stages: int):
        """
        Runs run_all_queued_without_pipelines the specified number of times.

        Will fail the test if there's not at least a single Task to be run.
        """

        for _ in range(num_pipeline_stages):
            self.run_all_queued_without_pipelines()

    def run_all_queued_without_pipelines(self):
        """
        Runs all currently queued tasks.  Enqueues pipeline tasks (created with
        `Task.then()`) for the next call of run_all_queued_without_pipelines,
        but does not execute them.  This is useful for stepping through
        pipeline stages in your tests.

        You could also call run_all_queued_including_pipelines, but that's
        slower and less controlled, resulting in confusing test failures from
        later pipeline stages.

        Will fail the test if there's not at least a single Task to be run.
        """
        # __tracebackhide__ = True

        found_at_least_one_queued_task = False
        task = self.huey.dequeue()
        pipeline_tasks = []

        while task:
            found_at_least_one_queued_task = True
            task.execute()

            if task.on_complete:
                pipeline_tasks.append(task.on_complete)
            task = self.huey.dequeue()

        for task in pipeline_tasks:
            self.huey.enqueue(task)

        if not found_at_least_one_queued_task:
            pytest.fail("No tasks queued to run.")

    def run_all_queued_including_pipelines(self):
        """
        Runs all currently queued tasks and their pipelines, created with
        `Task.then()`.

        Will fail the test if there's not at least a single Task to be run.
        """
        # __tracebackhide__ = True

        found_at_least_one_queued_task = False
        task = self.huey.dequeue()

        while task:
            found_at_least_one_queued_task = True
            task.execute()

            if task.on_complete:
                task = task.on_complete
            else:
                task = self.huey.dequeue()

        if not found_at_least_one_queued_task:
            pytest.fail("No tasks queued to run.")


@pytest.fixture(scope="function")
def tasks():
    return Tasks()


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

    def provision_instance(
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


class DNS:
    """
    I interact with the pebble-challtestsrv process to add and clear DNS
    entries.  See
    https://github.com/letsencrypt/pebble/blob/master/cmd/pebble-challtestsrv/README.md
    for the API.
    """

    @dataclass
    class Entry:
        record_type: str
        host: str
        base: str
        target: str = ""
        value: str = ""

        def __post_init__(self):
            if self.record_type == "txt":
                requests.post(
                    self.base + f"/add-txt",
                    json={"host": self.host, "value": self.value},
                )
            elif self.record_type == "cname":
                requests.post(
                    self.base + f"/set-cname",
                    json={"host": self.host, "target": self.target},
                )
            else:
                raise Exception(f"unknown record type: {self.record_type}")

        def clear(self):
            requests.post(
                self.base + f"/clear-{self.record_type}", json={"host": self.host}
            )

    def __init__(self):
        self.base = "http://localhost:8055"
        self.entries = []

    def add_txt(self, host, value):
        self.entries.append(
            self.Entry(record_type="txt", host=host, value=value, base=self.base)
        )

    def add_cname(self, host, target=None):
        if not host.startswith("_acme-challenge"):
            raise Exception("host needs to start with _acme-challenge")

        if not target:
            target = f"{host}.domains.cloud.gov"
        self.entries.append(
            self.Entry(record_type="cname", host=host, target=target, base=self.base)
        )

    def clear_all(self):
        # Unfortunately, the pebble-challtestsrv doesn't expose a "clear-all"
        # endpoint.

        for entry in self.entries:
            entry.clear()
        self.entries = []


@pytest.fixture(scope="function")
def dns():
    dns = DNS()
    yield dns
    dns.clear_all()


@pytest.fixture(scope="session")
def app():
    _app = create_app()

    # The Exception errorhandler seems to be firing in testing mode.
    del _app.error_handler_spec["open_broker"][None][Exception]

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
