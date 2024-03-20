from contextlib import contextmanager

from botocore import stub

# How I would love to use Localstack or Moto instead.
# Unfortunately, neither (in the OSS free version) supports Route53
# and CloudFront.  So we've been reduced to using the "serviceable"
# `boto3.stubber`


class FakeAWS:
    """Base class for Fake* classes"""

    @classmethod
    @contextmanager
    def stubbing(cls, real_resource):
        with stub.Stubber(real_resource) as stubber:
            fake_resource = cls(stubber)
            yield fake_resource
            fake_resource.assert_no_pending_responses()

    def __init__(self, resource_stubber):
        self.stubber = resource_stubber

    def assert_no_pending_responses(self) -> None:
        self.stubber.assert_no_pending_responses()

    @property
    def ANY(self):
        return stub.ANY
