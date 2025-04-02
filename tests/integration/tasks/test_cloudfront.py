import pytest

from broker.tasks.cloudfront import (
    wait_for_distribution_disabled,
    create_distribution,
    update_distribution,
)
from broker.models import Operation, ServiceInstanceTypes
from broker.extensions import config

from tests.lib import factories


@pytest.fixture
def service_instance(
    clean_db,
    operation_id,
    service_instance_id,
    cloudfront_distribution_arn,
    dedicated_waf_web_acl_arn,
    instance_factory,
):
    if instance_factory == factories.CDNServiceInstanceFactory:
        service_instance = instance_factory.create(
            id=service_instance_id,
            domain_names=["example.com", "foo.com"],
            domain_internal="fake1234.cloudfront.net",
            route53_alias_hosted_zone="Z2FDTNDATAQYW2",
            cloudfront_distribution_id="FakeDistributionId",
            cloudfront_distribution_arn=cloudfront_distribution_arn,
            cloudfront_origin_hostname="origin_hostname",
            cloudfront_origin_path="origin_path",
            origin_protocol_policy="https-only",
            forwarded_headers=["HOST"],
        )
    elif instance_factory == factories.CDNDedicatedWAFServiceInstanceFactory:
        service_instance = instance_factory.create(
            id=service_instance_id,
            domain_names=["example.com", "foo.com"],
            domain_internal="fake1234.cloudfront.net",
            route53_alias_hosted_zone="Z2FDTNDATAQYW2",
            cloudfront_distribution_id="FakeDistributionId",
            cloudfront_distribution_arn=cloudfront_distribution_arn,
            cloudfront_origin_hostname="origin_hostname",
            cloudfront_origin_path="origin_path",
            origin_protocol_policy="https-only",
            forwarded_headers=["HOST"],
            dedicated_waf_web_acl_arn=dedicated_waf_web_acl_arn,
        )
    new_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        leaf_pem="SOMECERTPEM",
        fullchain_pem="FULLCHAINOFSOMECERTPEM",
        id=1002,
    )
    current_cert = factories.CertificateFactory.create(
        service_instance=service_instance,
        private_key_pem="SOMEPRIVATEKEY",
        iam_server_certificate_id="certificate_id",
        id=1001,
    )
    service_instance.current_certificate = current_cert
    service_instance.new_certificate = new_cert
    clean_db.session.add(service_instance)
    clean_db.session.add(current_cert)
    clean_db.session.add(new_cert)
    clean_db.session.commit()
    clean_db.session.expunge_all()
    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )
    return service_instance


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_cloudfront_wait_distribution_disabled(
    clean_db,
    service_instance,
    operation_id,
    cloudfront,
):
    cloudfront.expect_get_distribution(
        caller_reference="asdf",
        domains=service_instance.domain_names,
        certificate_id=service_instance.new_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
        status="In progress",
        enabled=True,
    )
    cloudfront.expect_get_distribution(
        caller_reference="asdf",
        domains=service_instance.domain_names,
        certificate_id=service_instance.new_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
        status="In progress",
        enabled=False,
    )
    cloudfront.expect_get_distribution(
        caller_reference="asdf",
        domains=service_instance.domain_names,
        certificate_id=service_instance.new_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
        status="Deployed",
        enabled=False,
    )

    wait_for_distribution_disabled.call_local(operation_id)

    # asserts that all the mocked calls above were made
    cloudfront.assert_no_pending_responses()

    clean_db.session.expunge_all()

    operation = clean_db.session.get(Operation, operation_id)
    assert (
        operation.step_description == "Waiting for CloudFront distribution to disable"
    )


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_cloudfront_wait_distribution_disabled_error_max_retries(
    service_instance,
    operation_id,
    cloudfront,
):
    for _ in range(config.AWS_POLL_MAX_ATTEMPTS):
        cloudfront.expect_get_distribution(
            caller_reference="asdf",
            domains=service_instance.domain_names,
            certificate_id=service_instance.new_certificate.iam_server_certificate_id,
            origin_hostname=service_instance.cloudfront_origin_hostname,
            origin_path=service_instance.cloudfront_origin_path,
            distribution_id=service_instance.cloudfront_distribution_id,
            status="In progress",
            enabled=False,
        )

    with pytest.raises(RuntimeError):
        wait_for_distribution_disabled.call_local(operation_id)

    # asserts that all the mocked calls above were made
    cloudfront.assert_no_pending_responses()


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_cloudfront_create_distribution(
    clean_db,
    service_instance,
    operation_id,
    cloudfront,
):
    cloudfront.expect_get_distribution_returning_no_such_distribution(
        distribution_id=service_instance.cloudfront_distribution_id,
    )

    if service_instance.instance_type == ServiceInstanceTypes.CDN.value:
        cloudfront.expect_create_distribution_with_tags(
            caller_reference=service_instance.id,
            domains=service_instance.domain_names,
            certificate_id=service_instance.new_certificate.iam_server_certificate_id,
            origin_hostname=service_instance.cloudfront_origin_hostname,
            origin_path=service_instance.cloudfront_origin_path,
            distribution_id=service_instance.cloudfront_distribution_id,
            distribution_hostname=service_instance.cloudfront_origin_hostname,
            bucket_prefix=f"{service_instance.id}/",
        )
    elif service_instance.instance_type == ServiceInstanceTypes.CDN_DEDICATED_WAF.value:
        cloudfront.expect_create_distribution_with_tags(
            caller_reference=service_instance.id,
            domains=service_instance.domain_names,
            certificate_id=service_instance.new_certificate.iam_server_certificate_id,
            origin_hostname=service_instance.cloudfront_origin_hostname,
            origin_path=service_instance.cloudfront_origin_path,
            distribution_id=service_instance.cloudfront_distribution_id,
            distribution_hostname=service_instance.cloudfront_origin_hostname,
            bucket_prefix=f"{service_instance.id}/",
            dedicated_waf_web_acl_arn=service_instance.dedicated_waf_web_acl_arn,
        )

    create_distribution.call_local(operation_id)

    # asserts that all the mocked calls above were made
    cloudfront.assert_no_pending_responses()

    clean_db.session.expunge_all()

    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Creating CloudFront distribution"


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.CDNServiceInstanceFactory,
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_cloudfront_update_distribution(
    clean_db,
    service_instance,
    operation_id,
    cloudfront,
):
    cloudfront.expect_get_distribution_config(
        caller_reference="asdf",
        domains=service_instance.domain_names,
        certificate_id=service_instance.new_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
    )

    if service_instance.instance_type == ServiceInstanceTypes.CDN.value:
        cloudfront.expect_update_distribution(
            caller_reference="asdf",
            domains=service_instance.domain_names,
            certificate_id=service_instance.new_certificate.iam_server_certificate_id,
            origin_hostname=service_instance.cloudfront_origin_hostname,
            origin_path=service_instance.cloudfront_origin_path,
            distribution_id=service_instance.cloudfront_distribution_id,
            distribution_hostname=service_instance.cloudfront_origin_hostname,
        )
        tags = []
    if service_instance.instance_type == ServiceInstanceTypes.CDN_DEDICATED_WAF.value:
        cloudfront.expect_update_distribution(
            caller_reference="asdf",
            domains=service_instance.domain_names,
            certificate_id=service_instance.new_certificate.iam_server_certificate_id,
            origin_hostname=service_instance.cloudfront_origin_hostname,
            origin_path=service_instance.cloudfront_origin_path,
            distribution_id=service_instance.cloudfront_distribution_id,
            distribution_hostname=service_instance.cloudfront_origin_hostname,
            dedicated_waf_web_acl_arn=service_instance.dedicated_waf_web_acl_arn,
        )
        tags = [{"Key": "has_dedicated_acl", "Value": "true"}]

    cloudfront.expect_tag_resource(service_instance.cloudfront_distribution_arn, tags)

    update_distribution.call_local(operation_id)

    # asserts that all the mocked calls above were made
    cloudfront.assert_no_pending_responses()

    clean_db.session.expunge_all()

    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Updating CloudFront distribution"


@pytest.mark.parametrize(
    "instance_factory",
    [
        factories.CDNDedicatedWAFServiceInstanceFactory,
    ],
)
def test_cloudfront_update_distribution_already_has_tags(
    clean_db,
    service_instance,
    operation_id,
    cloudfront,
):
    tags = [{"Key": "has_dedicated_acl", "Value": "true"}]
    service_instance.tags = tags
    clean_db.session.add(service_instance)
    clean_db.session.commit()

    cloudfront.expect_get_distribution_config(
        caller_reference="asdf",
        domains=service_instance.domain_names,
        certificate_id=service_instance.new_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
    )

    cloudfront.expect_update_distribution(
        caller_reference="asdf",
        domains=service_instance.domain_names,
        certificate_id=service_instance.new_certificate.iam_server_certificate_id,
        origin_hostname=service_instance.cloudfront_origin_hostname,
        origin_path=service_instance.cloudfront_origin_path,
        distribution_id=service_instance.cloudfront_distribution_id,
        distribution_hostname=service_instance.cloudfront_origin_hostname,
        dedicated_waf_web_acl_arn=service_instance.dedicated_waf_web_acl_arn,
    )

    cloudfront.expect_tag_resource(service_instance.cloudfront_distribution_arn, tags)

    update_distribution.call_local(operation_id)

    # asserts that all the mocked calls above were made
    cloudfront.assert_no_pending_responses()

    clean_db.session.expunge_all()

    operation = clean_db.session.get(Operation, operation_id)
    assert operation.step_description == "Updating CloudFront distribution"
