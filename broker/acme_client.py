import datetime
import time

from acme.client import ClientV2
from acme import messages
from acme import errors


class AcmeClient(ClientV2):
    def get_cert_for_finalized_order(self, orderr, deadline):
        while datetime.datetime.now() < deadline:
            time.sleep(1)
            response = self._post_as_get(orderr.uri)
            body = messages.Order.from_json(response.json())
            if body.error is not None:
                raise errors.IssuanceError(body.error)
            if body.certificate is not None:
                certificate_response = self._post_as_get(body.certificate).text
                return orderr.update(body=body, fullchain_pem=certificate_response)
        raise errors.TimeoutError()
