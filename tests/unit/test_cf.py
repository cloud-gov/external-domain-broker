import pytest
import base64
import json
import uuid
import requests_mock

from broker.extensions import config
from broker.lib import cf
from requests import Response, exceptions


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
def cf_api_client():
    return cf.CFAPIClient()


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


def test_gets_access_token(access_token, access_token_response):
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )

        cfApiClient = cf.CFAPIClient()
        assert cfApiClient.get_access_token() == access_token


def test_get_access_token_error(cf_api_client):
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            status_code=500,
            additional_matcher=match_uaa_basic_auth,
        )

        with pytest.raises(exceptions.HTTPError):
            cf_api_client.get_access_token()


def test_refreshes_access_token(access_token):
    # expires_in = 0 so token should be immediately expired
    response = json.dumps({"access_token": access_token, "expires_in": 0})
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            text=response,
            additional_matcher=match_uaa_basic_auth,
        )

        cfApiClient = cf.CFAPIClient()
        assert cfApiClient.get_access_token() == access_token


def test_gets_space_name(
    space_guid, access_token, access_token_response, cf_api_client
):
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )

        response = json.dumps({"guid": space_guid, "name": "foobar-space"})
        m.get(
            f"http://mock.cf/v3/spaces/{space_guid}",
            text=response,
            request_headers={
                "Authorization": f"Bearer {access_token}",
            },
        )

        assert cf_api_client.get_space_name_by_guid(space_guid) == "foobar-space"


def test_gets_space_name_error(
    space_guid, access_token, access_token_response, cf_api_client
):
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )
        m.get(
            f"http://mock.cf/v3/spaces/{space_guid}",
            request_headers={
                "Authorization": f"Bearer {access_token}",
            },
            status_code=500,
        )
        with pytest.raises(exceptions.HTTPError):
            cf_api_client.get_space_name_by_guid(space_guid)


def test_gets_org_name(
    organization_guid, access_token, access_token_response, cf_api_client
):
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )
        response = json.dumps({"guid": organization_guid, "name": "org-1234"})
        m.get(
            f"http://mock.cf/v3/organizations/{organization_guid}",
            text=response,
            request_headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
        assert cf_api_client.get_org_name_by_guid(organization_guid) == "org-1234"


def test_gets_org_name_error(
    organization_guid, access_token, access_token_response, cf_api_client
):
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )
        m.get(
            f"http://mock.cf/v3/organizations/{organization_guid}",
            request_headers={
                "Authorization": f"Bearer {access_token}",
            },
            status_code=500,
        )
        with pytest.raises(exceptions.HTTPError):
            cf_api_client.get_org_name_by_guid(organization_guid)
