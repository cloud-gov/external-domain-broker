import logging
from datetime import date
import time

from botocore.exceptions import ClientError
from sqlalchemy import and_

from broker.aws import iam_commercial, iam_govcloud
from broker.extensions import config
from broker.lib.cdn import is_cdn_instance
from broker.models import Certificate
from broker.tasks.huey import pipeline_operation

logger = logging.getLogger(__name__)


@pipeline_operation("Uploading SSL certificate to AWS")
def upload_server_certificate(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    iam = _get_iam_client(service_instance)

    if is_cdn_instance(service_instance):
        iam_server_certificate_prefix = config.CLOUDFRONT_IAM_SERVER_CERTIFICATE_PREFIX
        propagation_time = 0
    else:
        iam_server_certificate_prefix = config.ALB_IAM_SERVER_CERTIFICATE_PREFIX
        propagation_time = config.IAM_CERTIFICATE_PROPAGATION_TIME

    _upload_server_certificate(
        db,
        iam,
        service_instance,
        iam_server_certificate_prefix,
        propagation_time,
    )


@pipeline_operation("Uploading SSL certificate to AWS")
def upload_cloudfront_server_certificate(operation_id: int, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    iam_server_certificate_prefix = config.CLOUDFRONT_IAM_SERVER_CERTIFICATE_PREFIX
    propagation_time = 0

    _upload_server_certificate(
        db,
        iam_commercial,
        service_instance,
        iam_server_certificate_prefix,
        propagation_time,
    )


@pipeline_operation("Removing SSL certificate from AWS")
def delete_server_certificate(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    iam = _get_iam_client(service_instance)

    if (
        service_instance.new_certificate is not None
        and service_instance.new_certificate.iam_server_certificate_name is not None
    ):
        _delete_server_certificate(iam, service_instance.new_certificate)

    if (
        service_instance.current_certificate is not None
        and service_instance.current_certificate.iam_server_certificate_name is not None
    ):
        _delete_server_certificate(iam, service_instance.current_certificate)


@pipeline_operation("Removing SSL certificate from AWS")
def delete_previous_server_certificate(operation_id: str, *, operation, db, **kwargs):
    service_instance = operation.service_instance
    iam = _get_iam_client(service_instance)
    _delete_previous_server_ceritficate(service_instance, iam, db)


@pipeline_operation("Removing SSL certificate from AWS")
def delete_previous_alb_server_certificate(
    operation_id: str, *, operation, db, **kwargs
):
    service_instance = operation.service_instance
    _delete_previous_server_ceritficate(service_instance, iam_govcloud, db)


def _upload_server_certificate(
    db,
    iam,
    service_instance,
    iam_server_certificate_prefix,
    propagation_time,
):
    if service_instance.new_certificate.iam_server_certificate_arn is not None:
        return

    certificate = service_instance.new_certificate

    today = date.today().isoformat()

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
        if "EntityAlreadyExists" in e.response["Error"]["Code"]:
            get_response = iam.get_server_certificate(
                ServerCertificateName=certificate.iam_server_certificate_name,
            )
            response = get_response["ServerCertificate"]
        else:
            logger.error(
                f"Got this code uploading server certificate: {e.response['Error']}"
            )
            raise e

    certificate.iam_server_certificate_id = response["ServerCertificateMetadata"][
        "ServerCertificateId"
    ]
    certificate.iam_server_certificate_arn = response["ServerCertificateMetadata"][
        "Arn"
    ]

    if service_instance.tags:
        iam.tag_server_certificate(
            ServerCertificateName=certificate.iam_server_certificate_name,
            Tags=service_instance.tags,
        )

    db.session.add(service_instance)
    db.session.add(certificate)
    db.session.commit()

    time.sleep(propagation_time)


def _delete_previous_server_ceritficate(service_instance, iam, db):
    certificates_to_delete = Certificate.query.filter(
        and_(
            Certificate.service_instance_id == service_instance.id,
            Certificate.id != service_instance.current_certificate_id,
        )
    ).all()
    for certificate in certificates_to_delete:
        _delete_server_certificate(iam, certificate)
        db.session.delete(certificate)

    db.session.commit()


def _delete_server_certificate(iam, certificate):
    cert_is_deleted = False
    try:
        iam.get_server_certificate(
            ServerCertificateName=certificate.iam_server_certificate_name
        )
    except ClientError as e:
        if "NoSuchEntity" in e.response["Error"]["Code"]:
            logger.info(
                f"Certificate {certificate.iam_server_certificate_name} not found, may have already been deleted",
            )
            cert_is_deleted = True

    if not cert_is_deleted:
        # now we know the cert exists, so any errors should be treated as unexpected
        iam.delete_server_certificate(
            ServerCertificateName=certificate.iam_server_certificate_name
        )


def _get_iam_client(service_instance):
    if is_cdn_instance(service_instance):
        iam = iam_commercial
    else:
        iam = iam_govcloud
    return iam
