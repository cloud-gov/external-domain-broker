import pytest  # noqa F401

from broker.extensions import db
from tests.lib.factories import ACMEUserFactory, ServiceInstanceFactory


def test_stores_acmeuser_private_key_pem_encrypted(client):
    si = ACMEUserFactory.create(private_key_pem="UNENCRYPTED")
    db.session.commit()
    row = db.engine.execute(
        f'select private_key_pem from acme_user where id="{si.id}"'
    ).first()
    assert row
    assert row[0] != "UNENCRYPTED"


def test_stores_service_instance_private_key_pem_encrypted(client):
    si = ServiceInstanceFactory.create(private_key_pem="UNENCRYPTED")
    db.session.commit()
    row = db.engine.execute(
        f'select private_key_pem from service_instance where id="{si.id}"'
    ).first()
    assert row
    assert row[0] != "UNENCRYPTED"
