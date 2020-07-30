import logging
from datetime import date

from botocore.exceptions import ClientError

from broker.aws import iam_commercial, iam_govcloud
from broker.extensions import config, db
from broker.models import Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.retriable_task
def upload_server_certificate(operation_id: int, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance
    certificate = service_instance.new_certificate

    operation.step_description = "Uploading SSL certificate to AWS"
    db.session.add(operation)
    db.session.commit()

    today = date.today().isoformat()
    if service_instance.instance_type == "cdn_service_instance":
        iam = iam_commercial
        iam_server_certificate_prefix = config.CLOUDFRONT_IAM_SERVER_CERTIFICATE_PREFIX
    else:
        iam = iam_govcloud
        iam_server_certificate_prefix = config.ALB_IAM_SERVER_CERTIFICATE_PREFIX
    certificate.iam_server_certificate_name = (
        f"{service_instance.id}-{today}-{certificate.id}"
    )
    try:
        response = iam.upload_server_certificate(
            Path=iam_server_certificate_prefix,
            ServerCertificateName=certificate.iam_server_certificate_name,
            CertificateBody=certificate.leaf_pem,
            PrivateKey=certificate.private_key_pem,
            CertificateChain=certificate.fullchain_pem,
        )
    except ClientError as e:
        if (
            e.response["Error"]["Code"] == "EntityAlreadyExistsException"
            and certificate.iam_server_certificate_id is not None
        ):
            return
        else:
            raise e

    certificate.iam_server_certificate_id = response["ServerCertificateMetadata"][
        "ServerCertificateId"
    ]
    certificate.iam_server_certificate_arn = response["ServerCertificateMetadata"][
        "Arn"
    ]
    db.session.add(service_instance)
    db.session.add(certificate)
    db.session.commit()


@huey.retriable_task
def delete_server_certificate(operation_id: str, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Removing SSL certificate from AWS"
    db.session.add(operation)
    db.session.commit()

    if service_instance.instance_type == "cdn_service_instance":
        iam = iam_commercial
    else:
        iam = iam_govcloud

    try:
        iam.delete_server_certificate(
            ServerCertificateName=service_instance.current_certificate.iam_server_certificate_name
        )
    except iam_commercial.exceptions.NoSuchEntityException:
        return
