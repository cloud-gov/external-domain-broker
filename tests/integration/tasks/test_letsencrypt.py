import pytest

from huey import CancelExecution

from broker.tasks.letsencrypt import (
    retrieve_certificate,
)


from tests.lib import factories


@pytest.fixture
def service_instance(clean_db, service_instance_id, operation_id):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id=service_instance_id,
        domain_names=["example.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
        forwarded_headers=["HOST"],
    )
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )
    return service_instance


def test_retrieve_certificate_cancels(clean_db, service_instance, operation_id, dns):
    dns.add_cname("_acme-challenge.example.com")

    with pytest.raises(CancelExecution):
        retrieve_certificate.call_local(operation_id)
