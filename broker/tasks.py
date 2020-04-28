import josepy
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from acme import client, messages

from . import db, huey
from .config import config_from_env


@huey.task()
def create_le_user(operation_id: str):
    from .models import ACMEUser, Operation

    acme_user = ACMEUser()
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    service_instance.acme_user = acme_user

    key = josepy.JWKRSA(
        key=rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
    )
    pem = key.key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    acme_user.private_key = pem

    net = client.ClientNetwork(key, user_agent="cloud.gov external domain broker")
    directory = messages.Directory.from_json(
        net.get(config_from_env().ACME_DIRECTORY).json()
    )
    client_acme = client.ClientV2(directory, net=net)

    acme_user.email = "cloud-gov-operations@gsa.gov"
    registration = client_acme.new_account(
        messages.NewRegistration.from_data(
            email=acme_user.email, terms_of_service_agreed=True
        )
    )
    acme_user.registration_json = registration.json_dumps()
    acme_user.uri = registration.uri
    db.session.add(operation)
    db.session.add(service_instance)
    db.session.add(acme_user)
    db.session.commit()
