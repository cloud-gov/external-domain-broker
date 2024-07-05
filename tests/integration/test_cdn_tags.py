import pytest  # noqa F401
import random
import uuid

from tests.lib.factories import (
    CDNServiceInstanceFactory,
    CDNDedicatedWAFServiceInstanceFactory,
)

from broker.tags import find_cdn_instances_without_tags


def test_no_cdn_instances_without_tags(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        CDNServiceInstanceFactory.create(id=str(uuid.uuid4()), tags={"foo": "bar"})
        CDNDedicatedWAFServiceInstanceFactory.create(
            id=str(uuid.uuid4()), tags={"foo": "bar"}
        )

        no_context_clean_db.session.commit()

        results = find_cdn_instances_without_tags()

        assert len(results) == 0


def test_finds_cdn_instances_without_tags(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        CDNServiceInstanceFactory.create(id=str(uuid.uuid4()), tags={"foo": "bar"})
        CDNDedicatedWAFServiceInstanceFactory.create(
            id=str(uuid.uuid4()), tags={"foo": "bar"}
        )
        cloudfront_arn_1 = f"arn-{random.choice(range(1000))}"
        cloudfront_arn_2 = f"arn-{random.choice(range(1000))}"
        cloudfront_arn_3 = f"arn-{random.choice(range(1000))}"

        CDNServiceInstanceFactory.create(
            id=str(uuid.uuid4()), cloudfront_distribution_arn=cloudfront_arn_1
        )
        CDNServiceInstanceFactory.create(
            id=str(uuid.uuid4()), cloudfront_distribution_arn=cloudfront_arn_2
        )
        CDNDedicatedWAFServiceInstanceFactory.create(
            id=str(uuid.uuid4()), cloudfront_distribution_arn=cloudfront_arn_3
        )

        no_context_clean_db.session.commit()

        results = find_cdn_instances_without_tags()

        assert results == [
            (cloudfront_arn_1,),
            (cloudfront_arn_2,),
            (cloudfront_arn_3,),
        ]
