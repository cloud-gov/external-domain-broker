import pytest
from sqlalchemy import insert

from broker.models import (
    CDNServiceInstance,
    CDNDedicatedWAFServiceInstance,
    ServiceInstanceTypes,
)


@pytest.fixture
def unmigrated_cdn_service_instance_operation_id(
    clean_db, client, service_instance_id, cloudfront_distribution_arn
):
    # Create a CDN instance manually to simulate an instance that
    # was created in the database before the new columns for the
    # cdn_dedicated_waf_service_instance were added
    create_cdn_instance_statement = insert(CDNServiceInstance).values(
        id=service_instance_id,
        domain_names=["example.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        origin_protocol_policy="https-only",
        forwarded_headers=["HOST"],
        route53_health_checks=None,
        dedicated_waf_web_acl_arn=None,
        dedicated_waf_web_acl_id=None,
        dedicated_waf_web_acl_name=None,
        shield_associated_health_check=None,
        cloudwatch_health_check_alarms=None,
        cloudfront_distribution_arn=cloudfront_distribution_arn,
        instance_type=ServiceInstanceTypes.CDN.value,
    )
    clean_db.session.execute(create_cdn_instance_statement)

    client.update_cdn_to_cdn_dedicated_waf_instance(service_instance_id)
    operation_id = client.response.json["operation"]
    return operation_id


@pytest.fixture
def unmigrated_cdn_dedicated_waf_service_instance_operation_id(
    clean_db, client, service_instance_id, cloudfront_distribution_arn
):
    # Create a CDN instance manually to simulate an instance that
    # was created in the database before the new columns for the
    # cdn_dedicated_waf_service_instance were added
    create_cdn_instance_statement = insert(CDNDedicatedWAFServiceInstance).values(
        id=service_instance_id,
        domain_names=["example.com"],
        domain_internal="fake1234.cloudfront.net",
        route53_alias_hosted_zone="Z2FDTNDATAQYW2",
        origin_protocol_policy="https-only",
        forwarded_headers=["HOST"],
        route53_health_checks=None,
        dedicated_waf_web_acl_arn=None,
        dedicated_waf_web_acl_id=None,
        dedicated_waf_web_acl_name=None,
        shield_associated_health_check=None,
        cloudwatch_health_check_alarms=None,
        cloudfront_distribution_arn=cloudfront_distribution_arn,
        instance_type=ServiceInstanceTypes.CDN.value,
    )
    clean_db.session.execute(create_cdn_instance_statement)

    client.update_cdn_to_cdn_dedicated_waf_instance(service_instance_id)
    operation_id = client.response.json["operation"]
    return operation_id
