import pytest  # noqa F401

from sqlalchemy import text

from broker.extensions import db
from tests.lib.factories import (
    ACMEUserFactory,
    ALBServiceInstanceFactory,
    CertificateFactory,
)


def test_stores_acmeuser_private_key_pem_encrypted(client):

    si = ACMEUserFactory.create(private_key_pem="UNENCRYPTED")
    db.session.commit()
    with db.engine.connect() as conn:
        row = conn.execute(
            text(f"select private_key_pem from acme_user where id='{si.id}'")
        ).first()
    
    assert row
    assert row[0] != "UNENCRYPTED"


def test_stores_service_instance_private_key_pem_encrypted(client):

    si = ALBServiceInstanceFactory.create()
    cert = CertificateFactory.create(service_instance=si, private_key_pem="UNENCRYPTED")
    db.session.commit()
    with db.engine.connect() as conn:
        row = conn.execute(
            text(f"select private_key_pem from certificate where id='{cert.id}'")
        ).first()
    
    assert row
    assert row[0] != "UNENCRYPTED"
