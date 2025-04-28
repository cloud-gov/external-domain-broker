import pytest
import random
import uuid
from datetime import date


@pytest.fixture
def service_instance_id():
    return str(random.randrange(0, 10000))


@pytest.fixture
def operation_id():
    return str(random.randrange(0, 10000))


@pytest.fixture
def new_cert_id():
    return str(random.randrange(0, 10000))


@pytest.fixture
def current_cert_id():
    return str(random.randrange(0, 10000))


@pytest.fixture
def cloudfront_distribution_arn():
    return str(uuid.uuid4())


@pytest.fixture
def protection_id():
    return str(uuid.uuid4())


@pytest.fixture
def dedicated_waf_web_acl_arn():
    return str(uuid.uuid4())


def get_server_certificate_name(instance_id, certificate_id):
    today = date.today().isoformat()
    return f"{instance_id}-{today}-{certificate_id}"


@pytest.fixture(scope="session")
def cache_policy_id():
    return str(uuid.uuid4())
