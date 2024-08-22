import requests
from functools import cache
from time import time
from urllib.parse import urljoin

from broker.extensions import config


class CFAPIClient:
    _access_token: str
    _expires_at: int

    def __init__(self):
        self.set_access_token()

    def set_access_token(self):
        if hasattr(self, "_access_token"):
            return

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
        r.raise_for_status()
        response = r.json()
        self._access_token = response["access_token"]
        # expires_at = current time in seconds + number of seconds until token expires
        self._expires_at = int(time()) + response["expires_in"]

    def get_access_token(self):
        return self._access_token

    @cache
    def get_space_name_by_guid(self, space_guid):
        with requests.Session() as s:
            s.headers["Authorization"] = f"Bearer {self.get_access_token()}"
            url = urljoin(config.CF_API_URL, f"v3/spaces/{space_guid}")
            response = s.get(url)
            response.raise_for_status()
            data = response.json()
            return data["name"]

    @cache
    def get_org_name_by_guid(self, organization_guid):
        with requests.Session() as s:
            s.headers["Authorization"] = f"Bearer {self.get_access_token()}"
            url = urljoin(config.CF_API_URL, f"v3/organizations/{organization_guid}")
            response = s.get(url)
            response.raise_for_status()
            data = response.json()
            return data["name"]
