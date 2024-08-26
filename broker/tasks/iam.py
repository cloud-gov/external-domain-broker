import logging
from datetime import date
import time

from botocore.exceptions import ClientError
from sqlalchemy import and_
from sqlalchemy.orm.attributes import flag_modified

from broker.aws import iam_commercial, iam_govcloud
from broker.extensions import config, db
from broker.lib.cdn import is_cdn_instance
from broker.models import Certificate, Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.retriable_task
def upload_server_certificate(operation_id: int, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance
    certificate = service_instance.new_certificate

    operation.step_description = "Uploading SSL certificate to AWS"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    today = date.today().isoformat()
    if is_cdn_instance(service_instance):
        iam = iam_commercial
        iam_server_certificate_prefix = config.CLOUDFRONT_IAM_SERVER_CERTIFICATE_PREFIX
        propagation_time = 0
    else:
        iam = iam_govcloud
        iam_server_certificate_prefix = config.ALB_IAM_SERVER_CERTIFICATE_PREFIX
        propagation_time = config.IAM_CERTIFICATE_PROPAGATION_TIME

    if service_instance.new_certificate.iam_server_certificate_arn is not None:
        return

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
        # TODO: there's an edge case here, where we uploaded the certificate but
        # failed to persist the metadata to the database. If that happens, we really
        # need to get the metadata back from IAM.
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

    tags = service_instance.tags if service_instance.tags else []
    iam.tag_server_certificate(
        ServerCertificateName=certificate.iam_server_certificate_name,
        Tags=tags,
    )

    time.sleep(propagation_time)


@huey.retriable_task
def delete_server_certificate(operation_id: str, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Removing SSL certificate from AWS"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if is_cdn_instance(service_instance):
        iam = iam_commercial
    else:
        iam = iam_govcloud

    if (
        service_instance.new_certificate is not None
        and service_instance.new_certificate.iam_server_certificate_name is not None
    ):
        try:
            iam.delete_server_certificate(
                ServerCertificateName=service_instance.new_certificate.iam_server_certificate_name
            )
        except iam_commercial.exceptions.NoSuchEntityException:
            pass

    if (
        service_instance.current_certificate is not None
        and service_instance.current_certificate.iam_server_certificate_name is not None
    ):
        try:
            iam.delete_server_certificate(
                ServerCertificateName=service_instance.current_certificate.iam_server_certificate_name
            )
        except iam_commercial.exceptions.NoSuchEntityException:
            return


@huey.retriable_task
def delete_previous_server_certificate(operation_id: str, **kwargs):
    operation = db.session.get(Operation, operation_id)
    service_instance = operation.service_instance

    operation.step_description = "Removing SSL certificate from AWS"
    flag_modified(operation, "step_description")
    db.session.add(operation)
    db.session.commit()

    if is_cdn_instance(service_instance):
        iam = iam_commercial
    else:
        iam = iam_govcloud

    for certificate in Certificate.query.filter(
        and_(
            Certificate.service_instance_id == service_instance.id,
            Certificate.id != service_instance.current_certificate_id,
        )
    ).all():
        try:
            iam.delete_server_certificate(
                ServerCertificateName=certificate.iam_server_certificate_name
            )
        except iam_commercial.exceptions.NoSuchEntityException:
            pass
        db.session.delete(certificate)

    db.session.commit()
