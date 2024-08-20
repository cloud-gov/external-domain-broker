import pytest  # noqa F401
import uuid

from broker.models import (
    CDNServiceInstance,
)

from tests.lib.cdn.provision import (
    subtest_provision_cdn_instance,
)
from tests.lib.cdn.update import (
    subtest_update_happy_path,
    subtest_update_same_domains,
)

# The subtests below are "interesting".  Before test_provision_happy_path, we
# had separate tests for each stage in the task pipeline.  But each test would
# have to duplicate much of the previous test.  This was arduous and slow. Now
# we have a single test_provision_happy_path, and many subtest_foo helper
# methods.  This still makes it clear which stage in the task pipeline is
# failing (look for the subtask_foo in the traceback), and allows us to re-use
# these subtasks when testing failure scenarios.


@pytest.fixture
def organization_guid():
    return str(uuid.uuid4())


@pytest.fixture
def space_guid():
    return str(uuid.uuid4())


def test_provision_happy_path(
    client,
    dns,
    tasks,
    route53,
    iam_commercial,
    simple_regex,
    cloudfront,
    organization_guid,
    space_guid,
):
    subtest_provision_cdn_instance(
        client,
        dns,
        tasks,
        route53,
        iam_commercial,
        simple_regex,
        cloudfront,
        organization_guid,
        space_guid,
    )
    instance_model = CDNServiceInstance
    subtest_update_happy_path(
        client,
        dns,
        tasks,
        route53,
        iam_commercial,
        simple_regex,
        cloudfront,
        instance_model,
    )
    subtest_update_same_domains(
        client,
        dns,
        tasks,
        route53,
        cloudfront,
        instance_model,
    )
