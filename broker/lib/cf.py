import requests
from urllib.parse import urljoin

from broker.extensions import config


def get_capi_access_token():
    r = requests.post(
        config.UAA_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
        },
        auth=requests.auth.HTTPBasicAuth(
            config.UAA_CLIENT_ID, config.UAA_CLIENT_SECRET
        ),
        timeout=config.REQUEST_TIMEOUT,
    )
    try:
        r.raise_for_status()
    except:
        return "Unexpected error", 500

    response = r.json()
    return response["access_token"]


def get_space_name_by_guid(space_guid, access_token):
    with requests.Session() as s:
        s.headers["Authorization"] = f"Bearer {access_token}"
        url = urljoin(config.CF_API_URL, f"v3/spaces/{space_guid}")
        response = s.get(url)
        return response["name"]


def get_org_name_by_guid(organization_guid, access_token):
    with requests.Session() as s:
        s.headers["Authorization"] = f"Bearer {access_token}"
        url = urljoin(config.CF_API_URL, f"v3/organizations/{organization_guid}")
        response = s.get(url)
        return response["name"]
