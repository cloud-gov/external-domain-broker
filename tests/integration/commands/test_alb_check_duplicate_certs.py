import pytest  # noqa F401

from tests.lib.factories import (
    CertificateFactory,
    ALBServiceInstanceFactory,
)

from broker.models import ALBServiceInstance

from broker.commands.duplicate_certs import (
    find_duplicate_alb_certs,
    log_duplicate_alb_cert_metrics,
    get_service_duplicate_alb_cert_count,
    get_and_log_service_duplicate_alb_cert_metric,
)


def test_no_duplicate_alb_certs(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        service_instance = ALBServiceInstanceFactory.create(id="1234")
        CertificateFactory.create(
            service_instance=service_instance,
        )

        no_context_clean_db.session.commit()

        results = find_duplicate_alb_certs(ALBServiceInstance)

        assert len(results) == 0


def test_non_current_duplicate_alb_cert(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        service_instance = ALBServiceInstanceFactory.create(id="1234")
        certificate = CertificateFactory.create(
            service_instance=service_instance,
        )
        CertificateFactory.create(
            service_instance=service_instance,
        )
        service_instance.current_certificate_id = certificate.id

        no_context_clean_db.session.commit()

        results = find_duplicate_alb_certs(ALBServiceInstance)

        assert len(results) == 1
        assert results == [("1234", 1)]


def test_multiple_non_current_duplicate_alb_certs(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        service_instance = ALBServiceInstanceFactory.create(id="1234")
        certificate = CertificateFactory.create(
            service_instance=service_instance,
        )
        CertificateFactory.create(
            service_instance=service_instance,
        )
        CertificateFactory.create(
            service_instance=service_instance,
        )
        service_instance.current_certificate_id = certificate.id

        no_context_clean_db.session.commit()

        results = find_duplicate_alb_certs(ALBServiceInstance)

        assert len(results) == 1
        assert results == [("1234", 2)]


def test_no_service_duplicate_alb_certs(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        service_instance = ALBServiceInstanceFactory.create(id="1234")
        CertificateFactory.create(
            service_instance=service_instance,
        )

        no_context_clean_db.session.commit()

        assert (
            get_service_duplicate_alb_cert_count(
                service_instance.id, ALBServiceInstance
            )
            == 0
        )


def test_service_duplicate_alb_certs(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        service_instance = ALBServiceInstanceFactory.create(id="1234")
        certificate = CertificateFactory.create(
            service_instance=service_instance,
        )
        CertificateFactory.create(
            service_instance=service_instance,
        )
        service_instance.current_certificate_id = certificate.id

        no_context_clean_db.session.commit()

        assert (
            get_service_duplicate_alb_cert_count(
                service_instance.id, ALBServiceInstance
            )
            == 1
        )


def test_service_duplicate_alb_certs_output(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        service_instance = ALBServiceInstanceFactory.create(id="1234")
        certificate = CertificateFactory.create(
            service_instance=service_instance,
        )
        CertificateFactory.create(
            service_instance=service_instance,
        )
        service_instance.current_certificate_id = certificate.id

        no_context_clean_db.session.commit()

        class FakeLogger:
            def __init__(self):
                self.output = ""

            def info(self, input):
                self.output = self.output + input

        fakeLogger = FakeLogger()

        get_and_log_service_duplicate_alb_cert_metric(
            service_instance.id, ALBServiceInstance, logger=fakeLogger
        )

        assert (
            fakeLogger.output.strip()
            == 'service_instance_duplicate_cert_count{service_instance_id="1234"} 1'
        )


def test_duplicate_alb_certs_output(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        service_instance = ALBServiceInstanceFactory.create(id="1234")
        certificate = CertificateFactory.create(
            service_instance=service_instance,
        )
        CertificateFactory.create(
            service_instance=service_instance,
        )
        CertificateFactory.create(
            service_instance=service_instance,
        )
        service_instance.current_certificate_id = certificate.id

        no_context_clean_db.session.commit()

        class FakeLogger:
            def __init__(self):
                self.output = ""

            def info(self, input):
                self.output = self.output + input

        fakeLogger = FakeLogger()

        log_duplicate_alb_cert_metrics(logger=fakeLogger)

        assert (
            fakeLogger.output.strip()
            == 'service_instance_duplicate_cert_count{service_instance_id="1234"} 2'
        )
