import requests
from urllib.parse import urljoin

from broker.extensions import config


def get_space_name_by_guid(space_guid, access_token):
    with requests.Session() as s:
        s.headers["Authorization"] = f"Bearer {access_token}"
        url = urljoin(config.CF_API_URL, f"v3/spaces/{space_guid}")
        response = s.get(url)
        data = response.json()
        return data["name"]


def get_org_name_by_guid(organization_guid, access_token):
    with requests.Session() as s:
        s.headers["Authorization"] = f"Bearer {access_token}"
        url = urljoin(config.CF_API_URL, f"v3/organizations/{organization_guid}")
        response = s.get(url)
        data = response.json()
        return data["name"]
