import pytest
import json
import uuid
import requests_mock

from broker.lib import cf
from requests import exceptions
from tests.lib.cf import match_uaa_basic_auth


@pytest.fixture
def cf_api_client():
    return cf.CFAPIClient()


def test_gets_access_token(access_token, access_token_response):
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )

        cfApiClient = cf.CFAPIClient()
        assert cfApiClient.access_token == access_token


def test_get_access_token_error(cf_api_client):
    with requests_mock.Mocker() as m:
        m.post(
            f"http://mock.uaa/token",
            status_code=500,
            additional_matcher=match_uaa_basic_auth,
        )

        with pytest.raises(exceptions.HTTPError):
            cf_api_client.access_token


def test_refreshes_access_token(access_token, cf_api_client):
    # expires immediately so token SHOULD BE refreshed
    access_token2 = str(uuid.uuid4())
    responses = [
        {
            "text": json.dumps({"access_token": access_token, "expires_in": 0}),
            "status_code": 200,
        },
        {
            "text": json.dumps({"access_token": access_token2, "expires_in": 0}),
            "status_code": 200,
        },
    ]

    with requests_mock.Mocker() as m:
        m.register_uri(
            "POST",
            "http://mock.uaa/token",
            responses,
            additional_matcher=match_uaa_basic_auth,
        )

        assert cf_api_client.access_token == access_token
        assert cf_api_client.access_token == access_token2
        assert m.call_count == 2


def test_does_not_refresh_access_token(access_token, cf_api_client):
    # expires in 35 seconds so token should NOT BE refreshed
    access_token_response = json.dumps({"access_token": access_token, "expires_in": 35})

    with requests_mock.Mocker() as m:
        m.post(
            "http://mock.uaa/token",
            text=access_token_response,
            additional_matcher=match_uaa_basic_auth,
        )

        assert cf_api_client.access_token == access_token
        assert cf_api_client.access_token == access_token
        assert m.call_count == 1


def test_gets_space_name(
    space_guid,
    access_token,
    cf_api_client,
    mock_with_uaa_auth,
):
    space_name = str(uuid.uuid4())
    response = json.dumps({"guid": space_guid, "name": space_name})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/spaces/{space_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert cf_api_client.get_space_name_by_guid(space_guid) == space_name


def test_gets_space_name_error(
    space_guid,
    access_token,
    cf_api_client,
    mock_with_uaa_auth,
):
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/spaces/{space_guid}",
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
        status_code=500,
    )
    with pytest.raises(exceptions.HTTPError):
        cf_api_client.get_space_name_by_guid(space_guid)


def test_gets_org_name(
    organization_guid, access_token, cf_api_client, mock_with_uaa_auth
):
    org_name = str(uuid.uuid4())
    response = json.dumps({"guid": organization_guid, "name": org_name})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/organizations/{organization_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert cf_api_client.get_organization_name_by_guid(organization_guid) == org_name


def test_gets_org_name_error(
    organization_guid,
    access_token,
    cf_api_client,
    mock_with_uaa_auth,
):
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/organizations/{organization_guid}",
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
        status_code=500,
    )
    with pytest.raises(exceptions.HTTPError):
        cf_api_client.get_organization_name_by_guid(organization_guid)
