import pytest

from broker.extensions import db
from broker.models import CDNServiceInstance, Challenge
from broker.tasks.letsencrypt import (
    create_user,
    retrieve_certificate,
    answer_challenges,
    generate_private_key,
    initiate_challenges,
)


from tests.lib import factories


@pytest.fixture
def service_instance():
    service_instance = factories.CDNServiceInstanceFactory.create(
        id="1234",
        domain_names=["example.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        cloudfront_distribution_id="FakeDistributionId",
        cloudfront_origin_hostname="origin_hostname",
        cloudfront_origin_path="origin_path",
        origin_protocol_policy="https-only",
        forwarded_headers=["HOST"],
    )
    db.session.refresh(service_instance)
    return service_instance


@pytest.fixture
def provision_operation(service_instance):
    operation = factories.OperationFactory.create(
        id=4321, service_instance=service_instance
    )
    return operation


def test_create_user_idempotent(clean_db, service_instance, provision_operation):

    # sanity check: the instance shouldn't yet have an acme user
    instance = db.session.get(CDNServiceInstance, "1234")
    assert instance.acme_user_id is None
    create_user.call_local(4321)
    db.session.expunge_all()
    instance = db.session.get(CDNServiceInstance, "1234")

    # ok, now it should have an acme user
    assert instance.acme_user_id is not None
    acme_id_before = instance.acme_user_id

    create_user.call_local(4321)
    instance_after = db.session.get(CDNServiceInstance, "1234")
    acme_id_after = instance_after.acme_user_id
    # make sure it's the same user now
    assert acme_id_before == acme_id_after


def test_generate_private_key_is_idempotent(
    clean_db, service_instance, provision_operation
):

    # make sure we have a user
    create_user.call_local(4321)

    instance = db.session.get(CDNServiceInstance, "1234")
    assert instance.acme_user is not None
    assert instance.new_certificate is None

    generate_private_key.call_local(4321)

    db.session.expunge_all()
    instance = db.session.get(CDNServiceInstance, "1234")
    assert instance.new_certificate.private_key_pem is not None
    stashed_key = instance.new_certificate.private_key_pem

    generate_private_key.call_local(4321)

    instance = db.session.get(CDNServiceInstance, "1234")
    assert stashed_key == instance.new_certificate.private_key_pem


def test_initiate_challenges_idempotent(
    clean_db, service_instance, provision_operation
):

    # make sure we have a user
    create_user.call_local(4321)
    generate_private_key.call_local(4321)
    instance = db.session.get(CDNServiceInstance, "1234")
    certificate = instance.new_certificate
    assert certificate.challenges.all() == []

    initiate_challenges.call_local(4321)
    instance = db.session.get(CDNServiceInstance, "1234")
    certificate = instance.new_certificate
    challenges = certificate.challenges.all()
    assert len(challenges) > 0
    db.session.expunge_all()

    initiate_challenges.call_local(4321)
    instance = db.session.get(CDNServiceInstance, "1234")
    certificate = instance.new_certificate
    challenges_after = certificate.challenges.all()
    assert len(challenges_after) == len(challenges)
    for i in range(len(challenges)):
        before = challenges[i]
        after = challenges_after[i]
        assert before.body_json == after.body_json


def test_answer_challenges_idempotent(
    clean_db, service_instance, provision_operation, dns
):
    dns.add_cname("_acme-challenge.example.com")

    # make sure we have a user
    create_user.call_local(4321)
    generate_private_key.call_local(4321)
    initiate_challenges.call_local(4321)

    instance = db.session.get(CDNServiceInstance, "1234")
    certificate = instance.new_certificate
    challenges_before = certificate.challenges.all()
    for challenge in challenges_before:
        assert not challenge.answered
    db.session.expunge_all()

    answer_challenges.call_local(4321)
    instance = db.session.get(CDNServiceInstance, "1234")
    certificate = instance.new_certificate
    challenges_before = certificate.challenges.all()
    example_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%example.com")
    ).first()
    dns.add_txt(
        "_acme-challenge.example.com.domains.cloud.test.",
        example_com_challenge.validation_contents,
    )
    db.session.expunge_all()
    answer_challenges.call_local(4321)
    answer_challenges.call_local(4321)
    instance = db.session.get(CDNServiceInstance, "1234")
    certificate = instance.new_certificate
    challenges_after = certificate.challenges.all()
    for i in range(len(challenges_after)):
        assert challenges_after[i].updated_at == challenges_before[i].updated_at


def test_retrieve_certificate_idempotent(
    clean_db, service_instance, provision_operation, dns
):
    dns.add_cname("_acme-challenge.example.com")

    # make sure we have a user
    create_user.call_local(4321)
    generate_private_key.call_local(4321)
    initiate_challenges.call_local(4321)
    service_instance = db.session.get(CDNServiceInstance, "1234")
    certificate = service_instance.new_certificate
    example_com_challenge = certificate.challenges.filter(
        Challenge.domain.like("%example.com")
    ).first()
    dns.add_txt(
        "_acme-challenge.example.com.domains.cloud.test.",
        example_com_challenge.validation_contents,
    )
    answer_challenges.call_local(4321)

    retrieve_certificate.call_local(4321)
    # no need to check stuff - acme raises if we try to get the same cert twice
    retrieve_certificate.call_local(4321)
