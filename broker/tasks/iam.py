import logging
from datetime import date

from broker.aws import iam
from broker.extensions import config, db
from broker.models import Operation
from broker.tasks import huey

logger = logging.getLogger(__name__)


@huey.retriable_task
def upload_server_certificate(operation_id: int, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    today = date.today().isoformat()
    iam_server_certificate_prefix = config.IAM_SERVER_CERTIFICATE_PREFIX
    service_instance.iam_server_certificate_name = f"{service_instance.id}-{today}"
    response = iam.upload_server_certificate(
        Path=iam_server_certificate_prefix,
        ServerCertificateName=service_instance.iam_server_certificate_name,
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


@huey.retriable_task
def delete_server_certificate(operation_id: str, **kwargs):
    operation = Operation.query.get(operation_id)
    service_instance = operation.service_instance

    try:
        iam.delete_server_certificate(
            ServerCertificateName=service_instance.iam_server_certificate_name
        )
    except iam.exceptions.NoSuchEntityException:
        return
