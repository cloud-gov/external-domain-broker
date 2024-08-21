import pytest
import json
import uuid
import requests
import requests_mock

from base64 import b64encode

from broker.lib import uaa
from broker.extensions import config


@pytest.fixture
def access_token():
    return str(uuid.uuid4())


def test_gets_access_token(access_token):
    with requests_mock.Mocker() as m:
        response = json.dumps({"access_token": access_token})
        basic_auth = requests.auth._basic_auth_str(
            config.UAA_CLIENT_ID, config.UAA_CLIENT_SECRET
        )

        m.post(
            f"http://mock.uaa/token",
            text=response,
            request_headers={
                "Authorization": basic_auth,
            },
        )

        assert uaa.get_uaa_access_token() == access_token
