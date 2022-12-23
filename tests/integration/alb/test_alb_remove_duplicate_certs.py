import pytest  # noqa F401

from broker.models import Operation
from tests.lib.factories import (
    CertificateFactory,
    ALBServiceInstanceFactory,
    OperationFactory,
)

from broker.duplicate_certs import (
  get_duplicate_certs_for_service,
  remove_duplicate_alb_certs,
  get_matching_alb_listener_arns_for_cert_arns,
  delete_duplicate_cert_db_record,
  delete_cert_record_and_resource
)
from broker.models import Certificate

def test_get_duplicate_certs_for_service(no_context_clean_db, no_context_app):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate1 = CertificateFactory.create(
        service_instance=service_instance,
    )
    certificate2 = CertificateFactory.create(
        service_instance=service_instance,
    )
    certificate3 = CertificateFactory.create(
        service_instance=service_instance,
    )
    service_instance.current_certificate_id = certificate1.id

    no_context_clean_db.session.commit()

    results = get_duplicate_certs_for_service(service_instance.id)

    assert len(results) == 2
    assert results == [certificate2, certificate3]

def test_get_matching_alb_listener_arns_for_single_cert_arn(alb):
    alb.expect_get_certificates_for_listener("listener-arn-0", 1)
    results = get_matching_alb_listener_arns_for_cert_arns(
      ["listener-arn-0/certificate-arn"],
      ["listener-arn-0"]
    )
    assert results == {
      "listener-arn-0/certificate-arn": "listener-arn-0"
    }

def test_get_matching_alb_listener_arns_breaks_correctly(alb):
    class FakeALBTest:
      def __init__(self):
        self.requested_listener_arns = []

      def describe_listener_certificates(self, ListenerArn=""):
        self.requested_listener_arns.append(ListenerArn)
        return {
          "Certificates": [{
            "CertificateArn": "listener-arn-0/certificate-arn"
          }],
        }
    
    fakeAlbTester = FakeALBTest()
    get_matching_alb_listener_arns_for_cert_arns(
      ["listener-arn-0/certificate-arn"],
      ["listener-arn-0", "listener-arn-1"],
      alb=fakeAlbTester
    )
    # Only request for the first listener was made because it
    # contained all of the specified certificate ARNs
    assert fakeAlbTester.requested_listener_arns == [
      "listener-arn-0"
    ]

def test_get_matching_alb_listener_arns_for_multiple_cert_arns(alb):
    alb.expect_get_certificates_for_listener("listener-arn-0", 1)
    results = get_matching_alb_listener_arns_for_cert_arns([
      "listener-arn-0/certificate-arn",
      "listener-arn-0/certificate-arn-0"
    ], [
      "listener-arn-0"
    ])
    assert results == {
      "listener-arn-0/certificate-arn": "listener-arn-0",
      "listener-arn-0/certificate-arn-0": "listener-arn-0"
    }

def test_get_matching_alb_listener_arns_for_multiple_listeners(alb):
    alb.expect_get_certificates_for_listener("listener-arn-0", 4)
    alb.expect_get_certificates_for_listener("listener-arn-1", 2)
    results = get_matching_alb_listener_arns_for_cert_arns([
      "listener-arn-0/certificate-arn-0",
      "listener-arn-0/certificate-arn-2",
      "listener-arn-1/certificate-arn-1",
    ], [
      "listener-arn-0",
      "listener-arn-1"
    ])
    assert results == {
      "listener-arn-0/certificate-arn-0": "listener-arn-0",
      "listener-arn-0/certificate-arn-2": "listener-arn-0",
      "listener-arn-1/certificate-arn-1": "listener-arn-1"
    }

def test_delete_cert_record_success(no_context_app, no_context_clean_db, alb):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate = CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn1"
    )
    no_context_clean_db.session.commit()

    assert len(Certificate.query.all()) == 1

    alb.expect_remove_certificate_from_listener("1234", "arn1")

    delete_cert_record_and_resource(certificate, "1234")

    assert len(Certificate.query.all()) == 0

def test_delete_duplicate_cert_record_rollback(no_context_app, no_context_clean_db):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate = CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn1"
    )
    no_context_clean_db.session.commit()

    assert len(Certificate.query.all()) == 1

    delete_duplicate_cert_db_record(certificate)
    no_context_clean_db.session.rollback()

    assert len(Certificate.query.all()) == 1

def test_delete_duplicate_cert_record_commit(no_context_app, no_context_clean_db):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate = CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn1"
    )
    no_context_clean_db.session.commit()

    assert len(Certificate.query.all()) == 1

    delete_duplicate_cert_db_record(certificate)
    no_context_clean_db.session.commit()

    assert len(Certificate.query.all()) == 0

def test_delete_cert_record_and_resource_handle_exception(no_context_clean_db, no_context_app):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate = CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn1"
    )

    no_context_clean_db.session.commit()

    assert len(Certificate.query.all()) == 1

    class FakeALBTest:
      def remove_listener_certificates(self, ListenerArn="", Certificates=[]):
        raise Exception("fail")
    
    fakeAlbTest = FakeALBTest()
    delete_cert_record_and_resource(certificate, "1234", alb=fakeAlbTest)

    assert len(Certificate.query.all()) == 1

def test_delete_cert_record_and_resource_success(no_context_clean_db, no_context_app, alb):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate = CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn1"
    )

    no_context_clean_db.session.commit()

    assert len(Certificate.query.all()) == 1

    alb.expect_remove_certificate_from_listener(service_instance.id, "arn1")
    delete_cert_record_and_resource(certificate, "1234")

    assert len(Certificate.query.all()) == 0

def test_remove_duplicate_certs_with_active_operations(no_context_clean_db, no_context_app, alb):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate1 = CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn1"
    )
    CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn2"
    )
    OperationFactory.create(
      service_instance=service_instance,
      state=Operation.States.IN_PROGRESS.value,
      action=Operation.Actions.RENEW.value
    )
    service_instance.current_certificate_id = certificate1.id
    no_context_clean_db.session.commit()

    results = get_duplicate_certs_for_service(service_instance.id)
    assert len(results) == 1
    
    remove_duplicate_alb_certs(listener_arns=[service_instance.id])
    
    # nothing should get deleted if there are active operations for a service instance
    results = get_duplicate_certs_for_service(service_instance.id)
    assert len(results) == 1


def test_remove_duplicate_certs_for_service(no_context_clean_db, no_context_app, alb):
  with no_context_app.app_context():
    service_instance = ALBServiceInstanceFactory.create(id="1234")
    certificate1 = CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn1"
    )
    CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn2"
    )
    CertificateFactory.create(
        service_instance=service_instance,
        iam_server_certificate_arn="arn3"
    )
    service_instance.current_certificate_id = certificate1.id
    no_context_clean_db.session.commit()

    alb.expect_get_certificates_for_listener(service_instance.id, certificates=[{
      "CertificateArn": "arn2"
    }, {
      "CertificateArn": "arn3"
    }])
    alb.expect_remove_certificate_from_listener(service_instance.id, "arn2")
    alb.expect_remove_certificate_from_listener(service_instance.id, "arn3")

    no_context_clean_db.session.commit()

    results = get_duplicate_certs_for_service(service_instance.id)
    assert len(results) == 2
    
    remove_duplicate_alb_certs(listener_arns=[service_instance.id])
    
    results = get_duplicate_certs_for_service(service_instance.id)
    assert len(results) == 0
