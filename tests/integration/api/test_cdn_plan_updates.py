import pytest  # noqa F401

from broker.models import CDNDedicatedWAFServiceInstance
from tests.lib import factories


@pytest.fixture
def service_instance(clean_db, service_instance_id):
    service_instance = factories.CDNServiceInstanceFactory.create(
        id=service_instance_id,
        domain_names=["example.com", "foo.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        iam_server_certificate_arn="certificate_arn",
        iam_server_certificate_name="certificate_name",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1001,
    )
    service_instance.current_certificate = current_cert
    clean_db.session.add(service_instance)
    clean_db.session.add(current_cert)
    clean_db.session.commit()
    return service_instance


def test_update_cdn_dedicated_waf_no_alarm_notification_email(
    clean_db, client, service_instance
):
    client.update_cdn_to_cdn_dedicated_waf_instance(service_instance.id)
    clean_db.session.expunge_all()

    assert client.response.status_code == 400, client.response.body


def test_update_cdn_dedicated_waf_with_alarm_notification_email(
    clean_db, client, service_instance
):
    assert not hasattr(service_instance, "alarm_notification_email")

    client.update_cdn_to_cdn_dedicated_waf_instance(
        service_instance.id, params={"alarm_notification_email": "foo@bar.com"}
    )
    clean_db.session.expunge_all()

    assert client.response.status_code == 202, client.response.body

    service_instance = clean_db.session.get(
        CDNDedicatedWAFServiceInstance, service_instance.id
    )
    assert service_instance.alarm_notification_email == "foo@bar.com"
