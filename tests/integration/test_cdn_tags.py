import pytest  # noqa F401
import random
import uuid

from tests.lib.factories import (
    CDNServiceInstanceFactory,
    CDNDedicatedWAFServiceInstanceFactory,
)

from broker.tags import find_cdn_instances_without_tags


@pytest.fixture
def cloudfront_ids():
    def _generate_ids(count):
        ids = []
        for i in range(count):
            ids.append(str(uuid.uuid4()))
        return ids

    return _generate_ids


@pytest.fixture
def cloudfront_arns():
    def _generate_arns(count):
        arns = []
        for i in range(count):
            arns.append(f"arn-{random.choice(range(1000))}")
        return arns

    return _generate_arns


def test_no_cdn_instances_without_tags(no_context_clean_db, no_context_app):
    with no_context_app.app_context():
        CDNServiceInstanceFactory.create(id=str(uuid.uuid4()), tags={"foo": "bar"})
        CDNDedicatedWAFServiceInstanceFactory.create(
            id=str(uuid.uuid4()), tags={"foo": "bar"}
        )

        no_context_clean_db.session.commit()

        results = find_cdn_instances_without_tags()

        assert len(results) == 0


def test_finds_cdn_instances_without_tags(
    no_context_clean_db, no_context_app, cloudfront_ids, cloudfront_arns
):
    with no_context_app.app_context():
        arns = cloudfront_arns(3)
        ids = cloudfront_ids(5)

        CDNServiceInstanceFactory.create(id=ids[0], tags={"foo": "bar"})
        CDNDedicatedWAFServiceInstanceFactory.create(id=ids[1], tags={"foo": "bar"})

        CDNServiceInstanceFactory.create(id=ids[2], cloudfront_distribution_arn=arns[0])
        CDNServiceInstanceFactory.create(id=ids[3], cloudfront_distribution_arn=arns[1])
        CDNDedicatedWAFServiceInstanceFactory.create(
            id=ids[4], cloudfront_distribution_arn=arns[2]
        )

        no_context_clean_db.session.commit()

        results = find_cdn_instances_without_tags()

        assert results == [
            (ids[2], arns[0]),
            (ids[3], arns[1]),
            (ids[4], arns[2]),
        ]
