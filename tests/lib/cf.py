import pytest
import requests_mock
import uuid
import json
import base64

from requests import Response

from broker.extensions import config


def match_uaa_basic_auth(request):
    basic_auth = bytes.decode(
        base64.b64encode(
            bytes(f"{config.UAA_CLIENT_ID}:{config.UAA_CLIENT_SECRET}", "utf-8")
        )
    )
    if request.headers["Authorization"] == f"Basic {basic_auth}":
        resp = Response()
        resp.status_code = 200
        return resp
    return None


@pytest.fixture
def space_guid():
    return str(uuid.uuid4())


@pytest.fixture
def organization_guid():
    return str(uuid.uuid4())


@pytest.fixture
def access_token():
    return str(uuid.uuid4())


@pytest.fixture
def access_token_response(access_token):
    return json.dumps({"access_token": access_token, "expires_in": 10})


@pytest.fixture
def request_mocker_with_auth_mock(access_token_response):
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )
        yield m
