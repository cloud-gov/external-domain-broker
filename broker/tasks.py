import josepy
import json
import OpenSSL
import time
from acme import challenges, client, crypto_util, messages
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from . import db, huey
from .config import config_from_env


def queue_all_provision_tasks_for_operation(operation_id: int):
    task_pipeline = (
        create_le_user.s(operation_id)
        .then(generate_private_key, operation_id)
        .then(initiate_challenges, operation_id)
        .then(update_txt_records, operation_id)
        .then(retrieve_certificate, operation_id)
    )
    huey.enqueue(task_pipeline)


@huey.task()
def create_le_user(operation_id: int):
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
    private_key_pem_in_binary = key.key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    acme_user.private_key_pem = private_key_pem_in_binary.decode("utf-8")

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


@huey.task()
def generate_private_key(operation_id: int):
    from .models import Operation

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    # Create private key.
    pkey = OpenSSL.crypto.PKey()
    pkey.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)

    # Get the PEM
    private_key_pem_in_binary = OpenSSL.crypto.dump_privatekey(
        OpenSSL.crypto.FILETYPE_PEM, pkey
    )

    # Get the CSR for the domains
    csr_pem_in_binary = crypto_util.make_csr(
        private_key_pem_in_binary, service_instance.domain_names
    )

    # Store them as text for later
    service_instance.private_key_pem = private_key_pem_in_binary.decode("utf-8")
    service_instance.csr_pem = csr_pem_in_binary.decode("utf-8")

    db.session.add(service_instance)
    db.session.add(operation)
    db.session.commit()


@huey.task()
def initiate_challenges(operation_id: int):
    from .models import Operation, Challenge

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    acme_user = service_instance.acme_user

    account_key = serialization.load_pem_private_key(
        acme_user.private_key_pem.encode(), password=None, backend=default_backend()
    )
    wrapped_account_key = josepy.JWKRSA(key=account_key)

    registration = json.loads(acme_user.registration_json)
    net = client.ClientNetwork(
        wrapped_account_key,
        user_agent="cloud.gov external domain broker",
        account=registration,
    )
    directory = messages.Directory.from_json(
        net.get(config_from_env().ACME_DIRECTORY).json()
    )
    client_acme = client.ClientV2(directory, net=net)

    order = client_acme.new_order(service_instance.csr_pem.encode())
    service_instance.order_json = json.dumps(order.to_json())

    challenge_body = dns_challenge(order)
    (
        challenge_response,
        challenge_validation_contents,
    ) = challenge_body.response_and_validation(wrapped_account_key)

    for domain in service_instance.domain_names:
        challenge = Challenge()
        challenge.body_json = challenge_body.json_dumps()

        challenge.domain = domain
        challenge.service_instance = service_instance
        challenge.validation_domain = challenge_body.validation_domain_name(domain)
        challenge.validation_contents = challenge_validation_contents
        db.session.add(challenge)

    db.session.commit()


@huey.task()
def update_txt_records(operation_id: int):
    from .models import Operation
    from .aws import route53

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    route53_responses = []

    for challenge in service_instance.challenges:
        domain = challenge.validation_domain
        contents = challenge.validation_contents
        route53_response = route53.change_resource_record_sets(
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "CREATE",
                        "ResourceRecordSet": {
                            "Type": "TXT",
                            "Name": f"{domain}.{config_from_env().DNS_ROOT_DOMAIN}",
                            "ResourceRecords": [{"Value": f'"{contents}"'}],
                            "TTL": 60,
                        },
                    },
                ],
            },
            HostedZoneId=config_from_env().ROUTE53_ZONE_ID,
        )
        route53_responses.append(route53_response)

    for route53_response in route53_responses:
        change_id = route53_response["ChangeInfo"]["Id"]
        waiter = route53.get_waiter("resource_record_sets_changed")
        waiter.wait(Id=change_id)


@huey.task()
def retrieve_certificate(operation_id: int):
    from .models import Operation

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    acme_user = service_instance.acme_user

    time.sleep(int(config_from_env().DNS_PROPAGATION_SLEEP_TIME))

    account_key = serialization.load_pem_private_key(
        acme_user.private_key_pem.encode(), password=None, backend=default_backend()
    )
    wrapped_account_key = josepy.JWKRSA(key=account_key)

    registration = json.loads(acme_user.registration_json)
    net = client.ClientNetwork(
        wrapped_account_key,
        user_agent="cloud.gov external domain broker",
        account=registration,
    )
    directory = messages.Directory.from_json(
        net.get(config_from_env().ACME_DIRECTORY).json()
    )
    client_acme = client.ClientV2(directory, net=net)

    for challenge in service_instance.challenges:
        challenge_body = messages.ChallengeBody.from_json(
            json.loads(challenge.body_json)
        )
        challenge_response = challenge_body.response(wrapped_account_key)
        # Let the CA server know that we are ready for the challenge.
        client_acme.answer_challenge(challenge_body, challenge_response)

    order_json = json.loads(service_instance.order_json)
    # The csr_pem in the JSON is a binary string, but finalize_order() expects
    # utf-8?  So we set it here from our saved copy.
    order_json["csr_pem"] = service_instance.csr_pem
    order = messages.OrderResource.from_json(order_json)
    finalized_order = client_acme.poll_and_finalize(order)

    service_instance.fullchain_pem = finalized_order.fullchain_pem
    db.session.add(service_instance)
    db.session.commit()


def dns_challenge(order):
    """Extract authorization resource from within order resource."""

    for authorization in order.authorizations:
        # authorization.body.challenges is a set of ChallengeBody objects.

        for challenge_body in authorization.body.challenges:
            if isinstance(challenge_body.chall, challenges.DNS01):
                return challenge_body
