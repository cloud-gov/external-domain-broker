import requests

from broker.extensions import config


def get_uaa_access_token():
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
