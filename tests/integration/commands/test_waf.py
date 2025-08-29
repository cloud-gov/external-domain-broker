import pytest

from broker.commands.waf import (
    create_dedicated_alb_waf_web_acls,
    wait_for_web_acl_to_exist,
    associate_dedicated_alb_waf_web_acls,
)
from broker.tasks.waf import generate_web_acl_name
from broker.aws import wafv2_govcloud as real_wafv2_govcloud
from broker.extensions import config
from broker.models import DedicatedALB
from tests.lib import factories


@pytest.fixture
def dedicated_alb(clean_db, dedicated_alb_id, dedicated_alb_arn):
    dedicated_alb = factories.DedicatedALBFactory.create(
        id=dedicated_alb_id, alb_arn=dedicated_alb_arn, dedicated_org="org-1"
    )
    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()
    return dedicated_alb


def test_wait_for_web_acl_to_exist(
    clean_db,
    wafv2_govcloud,
):
    wafv2_govcloud.expect_get_web_acl_not_found(arn="1234-dedicated-waf-arn")
    wafv2_govcloud.expect_get_web_acl_not_found(arn="1234-dedicated-waf-arn")
    wafv2_govcloud.expect_get_web_acl(arn="1234-dedicated-waf-arn")

    wait_for_web_acl_to_exist(real_wafv2_govcloud, "1234-dedicated-waf-arn", 3, 0)

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()


def test_wait_for_web_acl_to_exist_gives_up(
    clean_db,
    wafv2_govcloud,
):
    wafv2_govcloud.expect_get_web_acl_not_found(arn="1234-dedicated-waf-arn")
    wafv2_govcloud.expect_get_web_acl_not_found(arn="1234-dedicated-waf-arn")
    wafv2_govcloud.expect_get_web_acl_not_found(arn="1234-dedicated-waf-arn")
    wafv2_govcloud.expect_get_web_acl_not_found(arn="1234-dedicated-waf-arn")
    wafv2_govcloud.expect_get_web_acl_not_found(arn="1234-dedicated-waf-arn")

    with pytest.raises(RuntimeError):
        wait_for_web_acl_to_exist(real_wafv2_govcloud, "1234-dedicated-waf-arn", 5, 0)

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()


def test_create_dedicated_alb_waf_web_acls(
    clean_db,
    dedicated_alb_id,
    dedicated_alb,
    wafv2_govcloud,
):
    wafv2_govcloud.expect_alb_create_web_acl(
        dedicated_alb.dedicated_org,
        dedicated_alb.tags,
    )
    waf_web_acl_arn = f"arn:aws:wafv2::000000000000:global/webacl/{config.AWS_RESOURCE_PREFIX}-dedicated-org-alb-{dedicated_alb.dedicated_org}-waf"
    wafv2_govcloud.expect_get_web_acl(arn=waf_web_acl_arn)
    wafv2_govcloud.expect_put_logging_configuration(
        waf_web_acl_arn,
        config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    create_dedicated_alb_waf_web_acls()

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )

    assert service_instance.dedicated_waf_web_acl_arn
    assert service_instance.dedicated_waf_web_acl_id
    assert service_instance.dedicated_waf_web_acl_name


def test_create_dedicated_alb_waf_web_acls_does_nothing(
    clean_db,
    dedicated_alb_id,
    dedicated_alb,
    wafv2_govcloud,
):
    dedicated_alb.dedicated_waf_web_acl_id = "1234"
    dedicated_alb.dedicated_waf_web_acl_name = "1234-dedicated-waf"
    dedicated_alb.dedicated_waf_web_acl_arn = "1234-dedicated-waf-arn"
    dedicated_alb.dedicated_waf_associated = True

    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    create_dedicated_alb_waf_web_acls()

    wafv2_govcloud.assert_no_pending_responses()


def test_create_dedicated_alb_waf_web_acls_force_create(
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

    wafv2_govcloud.expect_alb_create_web_acl(
        dedicated_alb.dedicated_org,
        dedicated_alb.tags,
    )
    waf_web_acl_arn = f"arn:aws:wafv2::000000000000:global/webacl/{config.AWS_RESOURCE_PREFIX}-dedicated-org-alb-{dedicated_alb.dedicated_org}-waf"
    wafv2_govcloud.expect_get_web_acl(arn=waf_web_acl_arn)
    wafv2_govcloud.expect_put_logging_configuration(
        waf_web_acl_arn,
        config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    create_dedicated_alb_waf_web_acls(True)

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )

    assert service_instance.dedicated_waf_web_acl_arn == waf_web_acl_arn
    assert service_instance.dedicated_waf_web_acl_id
    assert service_instance.dedicated_waf_web_acl_name


def test_associate_dedicated_alb_waf_web_acls(
    clean_db, dedicated_alb_id, dedicated_alb, wafv2_govcloud
):
    dedicated_alb.dedicated_waf_web_acl_id = "1234"
    dedicated_alb.dedicated_waf_web_acl_name = "1234-dedicated-waf"
    dedicated_alb.dedicated_waf_web_acl_arn = "1234-dedicated-waf-arn"
    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    wafv2_govcloud.expect_alb_associate_web_acl(
        dedicated_alb.dedicated_waf_web_acl_arn,
        dedicated_alb.alb_arn,
    )

    associate_dedicated_alb_waf_web_acls()

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )

    assert service_instance.dedicated_waf_web_acl_arn
    assert service_instance.dedicated_waf_web_acl_id
    assert service_instance.dedicated_waf_web_acl_name
    assert service_instance.dedicated_waf_associated == True


def test_associate_dedicated_alb_does_nothing(
    clean_db, dedicated_alb_id, dedicated_alb, wafv2_govcloud
):
    associate_dedicated_alb_waf_web_acls()

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )

    assert not service_instance.dedicated_waf_web_acl_arn
    assert not service_instance.dedicated_waf_web_acl_id
    assert not service_instance.dedicated_waf_web_acl_name
    assert service_instance.dedicated_waf_associated == False
