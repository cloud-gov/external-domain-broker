import pytest
import random
import uuid


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
