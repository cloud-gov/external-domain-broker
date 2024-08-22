import datetime
import requests
from functools import cache
from time import time
from urllib.parse import urljoin

from broker.extensions import config


class CFAPIClient:
    _access_token: str
    _access_token_expiration: float

    def set_access_token(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
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

        expiration = now_utc + datetime.timedelta(seconds=response["expires_in"])
        self._access_token_expiration = expiration.timestamp()

    def get_access_token(self):
        if not hasattr(self, "_access_token") or self.is_token_expiring():
            self.set_access_token()
        return self._access_token

    def is_token_expiring(self):
        if hasattr(self, "_access_token_expiration"):
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if now_utc.timestamp() - self._access_token_expiration <= 30:
                return True
        return False

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
