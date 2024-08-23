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


@pytest.fixture(scope="function")
def space_guid():
    return str(uuid.uuid4())


@pytest.fixture(scope="function")
def organization_guid():
    return str(uuid.uuid4())


def generate_access_token():
    return str(uuid.uuid4())


@pytest.fixture(scope="function")
def access_token():
    return generate_access_token()


def generate_access_token_response(access_token):
    return json.dumps({"access_token": access_token, "expires_in": 0})


@pytest.fixture(scope="function")
def access_token_response(access_token):
    return generate_access_token_response(access_token)


@pytest.fixture(scope="function")
def mock_with_uaa_auth(access_token_response):
    with requests_mock.Mocker(real_http=True) as m:
        m.post(
            f"http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )
        yield m


@pytest.fixture(scope="function")
def mocked_cf_api(access_token, organization_guid, space_guid, mock_with_uaa_auth):
    response = json.dumps({"guid": space_guid, "name": "space-1234"})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/spaces/{space_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )
    response = json.dumps({"guid": organization_guid, "name": "org-1234"})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/organizations/{organization_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    yield mock_with_uaa_auth


def provision_instance_with_mocks(
    client, instance_model, organization_guid, space_guid, **kwargs
):
    access_token = generate_access_token()
    access_token_response = generate_access_token_response(access_token)

    with requests_mock.Mocker(real_http=True) as m:
        m.post(
            f"http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )

        response = json.dumps({"guid": space_guid, "name": "space-1234"})
        m.get(
            f"http://mock.cf/v3/spaces/{space_guid}",
            text=response,
            request_headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
        response = json.dumps({"guid": organization_guid, "name": "org-1234"})
        m.get(
            f"http://mock.cf/v3/organizations/{organization_guid}",
            text=response,
            request_headers={
                "Authorization": f"Bearer {access_token}",
            },
        )

        id = kwargs.get("id", "4321")
        params = kwargs.get("params", {})

        client.provision_instance(
            instance_model,
            id,
            params=params,
            organization_guid=organization_guid,
            space_guid=space_guid,
        )
