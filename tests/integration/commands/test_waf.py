import pytest

from broker.commands.waf import add_dedicated_alb_waf_web_acls
from broker.extensions import config
from broker.models import DedicatedALB
from tests.lib import factories


@pytest.fixture
def dedicated_alb(clean_db, dedicated_alb_id, service_instance_id, operation_id):
    dedicated_alb = factories.DedicatedALBFactory.create(
        id=dedicated_alb_id, alb_arn="alb-1", dedicated_org="org-1"
    )

    service_instance = factories.DedicatedALBServiceInstanceFactory.create(
        id=service_instance_id,
        org_id="org-1",
        alb_arn="alb-1",
        alb_listener_arn="listener-1",
    )

    clean_db.session.add(dedicated_alb)
    clean_db.session.add(service_instance)
    clean_db.session.commit()
    clean_db.session.expunge_all()

    factories.OperationFactory.create(
        id=operation_id, service_instance=service_instance
    )

    return dedicated_alb


def test_add_dedicated_alb_waf_web_acls(
    clean_db,
    dedicated_alb_id,
    dedicated_alb,
    wafv2_govcloud,
):
    wafv2_govcloud.expect_alb_create_web_acl(
        dedicated_alb_id,
    )
    wafv2_govcloud.expect_put_logging_configuration(
        f"arn:aws:wafv2::000000000000:global/webacl/{config.AWS_RESOURCE_PREFIX}-alb-{dedicated_alb_id}-dedicated-waf",
        config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    add_dedicated_alb_waf_web_acls()

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )

    assert service_instance.dedicated_waf_web_acl_arn
    assert service_instance.dedicated_waf_web_acl_id
    assert service_instance.dedicated_waf_web_acl_name


def test_add_dedicated_alb_waf_web_acls_does_nothing(
    clean_db,
    dedicated_alb_id,
    dedicated_alb,
    wafv2_govcloud,
):
    dedicated_alb.dedicated_waf_web_acl_id = "1234"
    dedicated_alb.dedicated_waf_web_acl_name = "1234-dedicated-waf"
    dedicated_alb.dedicated_waf_web_acl_arn = "1234-dedicated-waf-arn"

    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    add_dedicated_alb_waf_web_acls()

    wafv2_govcloud.assert_no_pending_responses()
