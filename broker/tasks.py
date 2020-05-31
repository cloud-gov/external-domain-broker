import json
import time
import re
from datetime import date, datetime, timedelta
from sqlalchemy.orm.attributes import flag_modified

from pprint import pp


import josepy
import OpenSSL
from acme import challenges, client, crypto_util, messages
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from broker.extensions import db, huey, config


def queue_all_provision_tasks_for_operation(operation_id: int):
    task_pipeline = (
        create_le_user.s(operation_id)
        .then(generate_private_key, operation_id)
        .then(initiate_challenges, operation_id)
        .then(create_TXT_records, operation_id)
        .then(wait_for_route53_changes, operation_id)
        .then(answer_challenges, operation_id)
        .then(retrieve_certificate, operation_id)
        .then(upload_certs_to_iam, operation_id)
        .then(create_cloudfront_distribution, operation_id)
        .then(wait_for_cloudfront_distribution, operation_id)
        .then(create_ALIAS_records, operation_id)
        .then(wait_for_route53_changes, operation_id)
        .then(mark_operation_as_succeeded, operation_id)
    )
    huey.enqueue(task_pipeline)


def queue_all_deprovision_tasks_for_operation(operation_id: int):
    task_pipeline = remove_ALIAS_records.s(operation_id).then(
        remove_TXT_records, operation_id
    )
    huey.enqueue(task_pipeline)


# Normal task, no retries
nonretriable_task = huey.task()

# These tasks retry every 10 miniutes for a day.
retriable_task = huey.task(retries=(6 * 24), retry_delay=(60 * 10))


@retriable_task
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
    directory = messages.Directory.from_json(net.get(config.ACME_DIRECTORY).json())
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


@nonretriable_task
def generate_private_key(operation_id: int):
    from .models import Operation

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    # Create private key.
    private_key = OpenSSL.crypto.PKey()
    private_key.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)

    # Get the PEM
    private_key_pem_in_binary = OpenSSL.crypto.dump_privatekey(
        OpenSSL.crypto.FILETYPE_PEM, private_key
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


class DNSChallengeNotFound(RuntimeError):
    def __init__(domain, obj):
        super().__init__(f"Cannot find DNS challenges for {domain} in {obj}")


class ChallengeNotFound(RuntimeError):
    def __init__(domain, obj):
        super().__init__(f"Cannot find any challenges for {domain} in {obj}")


def dns_challenge(order, domain):
    """Extract authorization resource from within order resource."""

    # authorization.body.challenges is a set of ChallengeBody
    # objects.
    challenges_for_domain = [
        authorization.body.challenges
        for authorization in order.authorizations
        if authorization.body.identifier.value == domain
    ][0]

    if not challenges_for_domain:
        raise ChallengeNotFound(domain, order.authorizations)

    for challenge in challenges_for_domain:
        if isinstance(challenge.chall, challenges.DNS01):
            return challenge

    raise DNSChallengeNotFound(domain, challenges_for_domain)


@retriable_task
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
    directory = messages.Directory.from_json(net.get(config.ACME_DIRECTORY).json())
    client_acme = client.ClientV2(directory, net=net)

    order = client_acme.new_order(service_instance.csr_pem.encode())
    service_instance.order_json = json.dumps(order.to_json())

    for domain in service_instance.domain_names:
        challenge_body = dns_challenge(order, domain)
        (
            challenge_response,
            challenge_validation_contents,
        ) = challenge_body.response_and_validation(wrapped_account_key)

        challenge = Challenge()
        challenge.body_json = challenge_body.json_dumps()

        challenge.domain = domain
        challenge.service_instance = service_instance
        challenge.validation_domain = challenge_body.validation_domain_name(domain)
        challenge.validation_contents = challenge_validation_contents
        db.session.add(challenge)

    db.session.commit()


@retriable_task
def create_TXT_records(operation_id: int):
    from .models import Operation
    from .aws import route53

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    for challenge in service_instance.challenges:
        domain = challenge.validation_domain
        txt_record = f"{domain}.{config.DNS_ROOT_DOMAIN}"
        contents = challenge.validation_contents
        print(f'Creating TXT record {txt_record} with contents "{contents}"')
        route53_response = route53.change_resource_record_sets(
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "CREATE",
                        "ResourceRecordSet": {
                            "Type": "TXT",
                            "Name": txt_record,
                            "ResourceRecords": [{"Value": f'"{contents}"'}],
                            "TTL": 60,
                        },
                    },
                ],
            },
            HostedZoneId=config.ROUTE53_ZONE_ID,
        )
        change_id = route53_response["ChangeInfo"]["Id"]
        print(f"Saving Route53 TXT change ID: {change_id}")
        service_instance.route53_change_ids.append(change_id)
        flag_modified(service_instance, "route53_change_ids")
        db.session.add(service_instance)
        db.session.commit()


@nonretriable_task
def remove_TXT_records(operation_id: int):
    from .models import Operation
    from .aws import route53

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    for challenge in service_instance.challenges:
        domain = challenge.validation_domain
        txt_record = f"{domain}.{config.DNS_ROOT_DOMAIN}"
        contents = challenge.validation_contents
        print(f'Removing TXT record {txt_record} with contents "{contents}"')
        route53_response = route53.change_resource_record_sets(
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "DELETE",
                        "ResourceRecordSet": {
                            "Type": "TXT",
                            "Name": txt_record,
                            "ResourceRecords": [{"Value": f'"{contents}"'}],
                            "TTL": 60,
                        },
                    },
                ],
            },
            HostedZoneId=config.ROUTE53_ZONE_ID,
        )
        change_id = route53_response["ChangeInfo"]["Id"]
        print(f"Ignoring Route53 TXT change ID: {change_id}")


@retriable_task
def wait_for_route53_changes(operation_id: int):
    from .models import Operation
    from .aws import route53

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    change_ids = service_instance.route53_change_ids.copy()
    print(f"Waiting for {len(change_ids)} Route53 change IDs: {change_ids}")
    for change_id in change_ids:
        print(f"Waiting for: {change_id}")
        waiter = route53.get_waiter("resource_record_sets_changed")
        waiter.wait(
            Id=change_id,
            WaiterConfig={
                "Delay": config.AWS_POLL_WAIT_TIME_IN_SECONDS,
                "MaxAttempts": config.AWS_POLL_MAX_ATTEMPTS,
            },
        )
        service_instance.route53_change_ids.remove(change_id)
        flag_modified(service_instance, "route53_change_ids")
        db.session.add(service_instance)
        db.session.commit()


@retriable_task
def answer_challenges(operation_id: int):
    from .models import Operation

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    acme_user = service_instance.acme_user

    time.sleep(int(config.DNS_PROPAGATION_SLEEP_TIME))

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
    directory = messages.Directory.from_json(net.get(config.ACME_DIRECTORY).json())
    client_acme = client.ClientV2(directory, net=net)

    for challenge in service_instance.challenges:
        challenge_body = messages.ChallengeBody.from_json(
            json.loads(challenge.body_json)
        )
        challenge_response = challenge_body.response(wrapped_account_key)
        # Let the CA server know that we are ready for the challenge.
        client_acme.answer_challenge(challenge_body, challenge_response)
        challenge.answered = True
        db.session.add(challenge)
        db.session.commit()


@retriable_task
def retrieve_certificate(operation_id: int):
    def cert_from_fullchain(fullchain_pem: str) -> str:
        """extract cert_pem from fullchain_pem

        Reference https://github.com/certbot/certbot/blob/b42e24178aaa3f1ad1323acb6a3a9c63e547893f/certbot/certbot/crypto_util.py#L482-L518
        """
        cert_pem_regex = re.compile(
            b"-----BEGIN CERTIFICATE-----\r?.+?\r?-----END CERTIFICATE-----\r?",
            re.DOTALL,  # DOTALL (/s) because the base64text may include newlines
        )

        certs = cert_pem_regex.findall(fullchain_pem.encode())
        if len(certs) < 2:
            raise RuntimeError(
                "failed to extract cert from fullchain: less than 2 certificates in chain"
            )

        certs_normalized = [
            OpenSSL.crypto.dump_certificate(
                OpenSSL.crypto.FILETYPE_PEM,
                OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert),
            ).decode()
            for cert in certs
        ]

        return certs_normalized[0]

    from .models import Operation

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
    directory = messages.Directory.from_json(net.get(config.ACME_DIRECTORY).json())
    client_acme = client.ClientV2(directory, net=net)

    order_json = json.loads(service_instance.order_json)
    # The csr_pem in the JSON is a binary string, but finalize_order() expects
    # utf-8?  So we set it here from our saved copy.
    order_json["csr_pem"] = service_instance.csr_pem
    order = messages.OrderResource.from_json(order_json)

    deadline = datetime.now() + timedelta(seconds=config.ACME_POLL_TIMEOUT_IN_SECONDS)
    finalized_order = client_acme.poll_and_finalize(orderr=order, deadline=deadline)

    service_instance.fullchain_pem = finalized_order.fullchain_pem
    service_instance.cert_pem = cert_from_fullchain(service_instance.fullchain_pem)
    db.session.add(service_instance)
    db.session.commit()


@retriable_task
def upload_certs_to_iam(operation_id: int):
    from .models import Operation
    from .aws import iam

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    today = date.today().isoformat()
    iam_server_certificate_prefix = config.IAM_SERVER_CERTIFICATE_PREFIX
    response = iam.upload_server_certificate(
        Path=iam_server_certificate_prefix,
        ServerCertificateName=f"{service_instance.id}-{today}",
        CertificateBody=service_instance.cert_pem,
        PrivateKey=service_instance.private_key_pem,
        CertificateChain=service_instance.fullchain_pem,
    )

    service_instance.iam_server_certificate_id = response["ServerCertificateMetadata"][
        "ServerCertificateId"
    ]
    service_instance.iam_server_certificate_arn = response["ServerCertificateMetadata"][
        "Arn"
    ]
    db.session.add(service_instance)
    db.session.commit()


@retriable_task
def create_cloudfront_distribution(operation_id: int):
    from .models import Operation
    from .aws import cloudfront

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    domains = service_instance.domain_names

    response = cloudfront.create_distribution(
        DistributionConfig={
            "CallerReference": service_instance.id,
            "Aliases": {"Quantity": len(domains), "Items": domains},
            "DefaultRootObject": "",
            "Origins": {
                "Quantity": 1,
                "Items": [
                    {
                        "Id": "default-origin",
                        "DomainName": service_instance.cloudfront_origin_hostname,
                        "OriginPath": service_instance.cloudfront_origin_path,
                        "CustomOriginConfig": {
                            "HTTPPort": 80,
                            "HTTPSPort": 443,
                            "OriginProtocolPolicy": "https-only",
                            "OriginSslProtocols": {
                                "Quantity": 1,
                                "Items": ["TLSv1.2"],
                            },
                            "OriginReadTimeout": 30,
                            "OriginKeepaliveTimeout": 5,
                        },
                    }
                ],
            },
            "OriginGroups": {"Quantity": 0},
            "DefaultCacheBehavior": {
                "TargetOriginId": "default-origin",
                "ForwardedValues": {
                    "QueryString": True,
                    "Cookies": {"Forward": "all"},
                    "Headers": {"Quantity": 1, "Items": ["HOST"]},
                    "QueryStringCacheKeys": {"Quantity": 0},
                },
                "TrustedSigners": {"Enabled": False, "Quantity": 0},
                "ViewerProtocolPolicy": "redirect-to-https",
                "MinTTL": 0,
                "AllowedMethods": {
                    "Quantity": 7,
                    "Items": [
                        "GET",
                        "HEAD",
                        "POST",
                        "PUT",
                        "PATCH",
                        "OPTIONS",
                        "DELETE",
                    ],
                    "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
                },
                "SmoothStreaming": False,
                "DefaultTTL": 86400,
                "MaxTTL": 31536000,
                "Compress": False,
                "LambdaFunctionAssociations": {"Quantity": 0},
            },
            "CacheBehaviors": {"Quantity": 0},
            "CustomErrorResponses": {"Quantity": 0},
            "Comment": "external domain service https://cloud-gov/external-domain-broker",
            "Logging": {
                "Enabled": False,
                "IncludeCookies": False,
                "Bucket": "",
                "Prefix": "",
            },
            "PriceClass": "PriceClass_100",
            "Enabled": True,
            "ViewerCertificate": {
                "CloudFrontDefaultCertificate": False,
                "IAMCertificateId": service_instance.iam_server_certificate_id,
                "SSLSupportMethod": "sni-only",
                "MinimumProtocolVersion": "TLSv1.2_2018",
            },
            "IsIPV6Enabled": True,
        }
    )

    service_instance.cloudfront_distribution_arn = response["Distribution"]["ARN"]
    service_instance.cloudfront_distribution_id = response["Distribution"]["Id"]
    service_instance.cloudfront_distribution_url = response["Distribution"][
        "DomainName"
    ]
    db.session.add(service_instance)
    db.session.commit()


@retriable_task
def wait_for_cloudfront_distribution(operation_id: str):
    from .models import Operation
    from .aws import cloudfront

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    waiter = cloudfront.get_waiter("distribution_deployed")
    waiter.wait(
        Id=service_instance.cloudfront_distribution_id,
        WaiterConfig={
            "Delay": config.AWS_POLL_WAIT_TIME_IN_SECONDS,
            "MaxAttempts": config.AWS_POLL_MAX_ATTEMPTS,
        },
    )


@retriable_task
def create_ALIAS_records(operation_id: str):
    from .models import Operation
    from .aws import route53

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    print(f"Creating ALIAS records for {service_instance.domain_names}")

    for domain in service_instance.domain_names:
        alias_record = f"{domain}.{config.DNS_ROOT_DOMAIN}"
        target = service_instance.cloudfront_distribution_url
        print(f'Creating ALIAS record {alias_record} pointing to "{target}"')
        route53_response = route53.change_resource_record_sets(
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "CREATE",
                        "ResourceRecordSet": {
                            "Type": "A",
                            "Name": alias_record,
                            "AliasTarget": {
                                "DNSName": target,
                                "HostedZoneId": "Z2FDTNDATAQYW2",
                                "EvaluateTargetHealth": False,
                            },
                        },
                    },
                ],
            },
            HostedZoneId=config.ROUTE53_ZONE_ID,
        )
        change_id = route53_response["ChangeInfo"]["Id"]
        print(f"Saving Route53 ALIAS change ID: {change_id}")
        service_instance.route53_change_ids.append(change_id)
        flag_modified(service_instance, "route53_change_ids")
        db.session.add(service_instance)
        db.session.commit()


@nonretriable_task
def remove_ALIAS_records(operation_id: str):
    from .models import Operation
    from .aws import route53

    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    print(f"Removing ALIAS records for {service_instance.domain_names}")

    for domain in service_instance.domain_names:
        alias_record = f"{domain}.{config.DNS_ROOT_DOMAIN}"
        target = service_instance.cloudfront_distribution_url
        print(f'Removing ALIAS record {alias_record} pointing to "{target}"')
        route53_response = route53.change_resource_record_sets(
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "DELETE",
                        "ResourceRecordSet": {
                            "Type": "A",
                            "Name": alias_record,
                            "AliasTarget": {
                                "DNSName": target,
                                "HostedZoneId": "Z2FDTNDATAQYW2",
                                "EvaluateTargetHealth": False,
                            },
                        },
                    },
                ],
            },
            HostedZoneId=config.ROUTE53_ZONE_ID,
        )
        change_id = route53_response["ChangeInfo"]["Id"]
        print(f"Not tracking change ID: {change_id}")


@retriable_task
def mark_operation_as_succeeded(operation_id: str):
    from .models import Operation

    operation = Operation.query.get(operation_id)
    operation.state = Operation.States.SUCCEEDED
    db.session.add(operation)
    db.session.commit()
