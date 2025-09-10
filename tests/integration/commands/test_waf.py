import pytest

from broker.commands.waf import (
    create_dedicated_alb_waf_web_acls,
    wait_for_web_acl_to_exist,
    update_dedicated_alb_waf_web_acls,
    wait_for_associated_waf_web_acl_arn,
)
from broker.tasks.waf import generate_web_acl_name
from broker.aws import wafv2_govcloud as real_wafv2_govcloud
from broker.extensions import config
from broker.models import DedicatedALB
from broker.tasks.waf import generate_web_acl_name
from tests.lib import factories
from tests.lib.identifiers import (
    generate_dedicated_alb_arn,
    generate_dedicated_alb_id,
)
from tests.lib.fake_wafv2 import (
    generate_fake_waf_web_acl_arn,
    generate_fake_waf_web_acl_id,
)


@pytest.fixture
def dedicated_alb(clean_db, dedicated_alb_id, dedicated_alb_arn, organization_guid):
    dedicated_alb = factories.DedicatedALBFactory.create(
        id=dedicated_alb_id, alb_arn=dedicated_alb_arn, dedicated_org=organization_guid
    )
    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()
    return dedicated_alb


@pytest.fixture
def dedicated_alb_waf_name(dedicated_alb):
    return generate_web_acl_name(dedicated_alb, config.AWS_RESOURCE_PREFIX)


@pytest.fixture
def dedicated_alb_waf_id(dedicated_alb_waf_name):
    return generate_fake_waf_web_acl_id(dedicated_alb_waf_name)


@pytest.fixture
def dedicated_alb_waf_arn(dedicated_alb_waf_name):
    return generate_fake_waf_web_acl_arn(dedicated_alb_waf_name)


def test_wait_for_web_acl_to_exist(
    clean_db, wafv2_govcloud, dedicated_alb_waf_name, dedicated_alb_waf_arn
):
    wafv2_govcloud.expect_get_web_acl_not_found(arn=dedicated_alb_waf_arn)
    wafv2_govcloud.expect_get_web_acl_not_found(arn=dedicated_alb_waf_arn)
    wafv2_govcloud.expect_get_web_acl(
        dedicated_alb_waf_name, params={"ARN": dedicated_alb_waf_arn}
    )

    wait_for_web_acl_to_exist(real_wafv2_govcloud, dedicated_alb_waf_arn, 3, 0)

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
    dedicated_alb_waf_name,
    dedicated_alb_waf_id,
    dedicated_alb_waf_arn,
):
    wafv2_govcloud.expect_alb_create_web_acl(
        dedicated_alb.dedicated_org,
        dedicated_alb.tags,
    )

    wafv2_govcloud.expect_get_web_acl(
        dedicated_alb_waf_name, params={"ARN": dedicated_alb_waf_arn}
    )
    wafv2_govcloud.expect_put_logging_configuration(
        dedicated_alb_waf_arn,
        config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    create_dedicated_alb_waf_web_acls()

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )

    assert service_instance.dedicated_waf_web_acl_arn == dedicated_alb_waf_arn
    assert service_instance.dedicated_waf_web_acl_id == dedicated_alb_waf_id
    assert service_instance.dedicated_waf_web_acl_name == dedicated_alb_waf_name


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
    dedicated_alb_waf_name,
    dedicated_alb_waf_id,
    dedicated_alb_waf_arn,
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

    waf_name = generate_web_acl_name(dedicated_alb, config.AWS_RESOURCE_PREFIX)
    waf_web_acl_arn = generate_fake_waf_web_acl_arn(waf_name)

    wafv2_govcloud.expect_get_web_acl(
        dedicated_alb_waf_name, params={"ARN": waf_web_acl_arn}
    )
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

    assert service_instance.dedicated_waf_web_acl_arn == dedicated_alb_waf_arn
    assert service_instance.dedicated_waf_web_acl_id == dedicated_alb_waf_id
    assert service_instance.dedicated_waf_web_acl_name == dedicated_alb_waf_name


def test_create_dedicated_alb_waf_web_acls_multiple_same_org(
    clean_db,
    dedicated_alb,
    wafv2_govcloud,
    dedicated_alb_waf_name,
    dedicated_alb_waf_id,
    dedicated_alb_waf_arn,
    organization_guid,
):
    dedicated_alb2 = factories.DedicatedALBFactory.create(
        id=generate_dedicated_alb_id(),
        alb_arn=generate_dedicated_alb_arn(),
        dedicated_org=organization_guid,
    )
    clean_db.session.add(dedicated_alb2)
    clean_db.session.commit()

    # Processing first dedicated ALB will create the web ACL
    wafv2_govcloud.expect_alb_create_web_acl(
        dedicated_alb.dedicated_org,
        dedicated_alb.tags,
    )
    wafv2_govcloud.expect_get_web_acl(
        dedicated_alb_waf_name, params={"ARN": dedicated_alb_waf_arn}
    )
    wafv2_govcloud.expect_put_logging_configuration(
        dedicated_alb_waf_arn,
        config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    # For second dedicated ALB, should find that web ACL already exists
    wafv2_govcloud.expect_alb_create_web_acl_already_exists(
        organization_guid, dedicated_alb.tags
    )
    # Get info about web ACL to set on second dedicated ALB
    wafv2_govcloud.expect_list_web_acls(
        [dedicated_alb_waf_name],
        params={
            "Scope": "REGIONAL",
        },
    )
    wafv2_govcloud.expect_put_logging_configuration(
        dedicated_alb_waf_arn,
        config.ALB_WAF_CLOUDWATCH_LOG_GROUP_ARN,
    )

    create_dedicated_alb_waf_web_acls(True)

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    dedicated_albs = DedicatedALB.query.all()
    assert len(dedicated_albs) == 2
    for dedicated_alb in dedicated_albs:
        assert dedicated_alb.dedicated_waf_web_acl_arn == dedicated_alb_waf_arn
        assert dedicated_alb.dedicated_waf_web_acl_id == dedicated_alb_waf_id
        assert dedicated_alb.dedicated_waf_web_acl_name == dedicated_alb_waf_name


def test_associate_dedicated_alb_updates_waf_web_acls(
    clean_db,
    dedicated_alb_id,
    dedicated_alb,
    wafv2_govcloud,
):
    dedicated_alb.dedicated_waf_web_acl_name = "1234-dedicated-waf"
    dedicated_alb.dedicated_waf_web_acl_arn = generate_fake_waf_web_acl_arn(
        dedicated_alb.dedicated_waf_web_acl_name
    )
    dedicated_alb.dedicated_waf_web_acl_id = generate_fake_waf_web_acl_id(
        dedicated_alb.dedicated_waf_web_acl_name
    )
    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    # Simulate case where actually associated WAF is different than what is
    # tracked in the database
    wafv2_govcloud.expect_get_web_acl_for_resource(
        dedicated_alb.alb_arn, "obsolete-waf"
    )
    # Associate the WAF tracked by the database with the ALB
    wafv2_govcloud.expect_alb_associate_web_acl(
        dedicated_alb.dedicated_waf_web_acl_arn,
        dedicated_alb.alb_arn,
    )
    # Confirm the association of the update WAF to the ALB
    wafv2_govcloud.expect_get_web_acl_for_resource(
        dedicated_alb.alb_arn, "1234-dedicated-waf"
    )
    # Check for obsolete WAF before deletion
    wafv2_govcloud.expect_get_web_acl(
        "obsolete-waf",
        params={
            "Id": generate_fake_waf_web_acl_id("obsolete-waf"),
            "Name": "obsolete-waf",
            "Scope": "REGIONAL",
        },
    )
    # Delete obsolete WAF
    wafv2_govcloud.expect_delete_web_acl(
        generate_fake_waf_web_acl_id("obsolete-waf"), "obsolete-waf", "REGIONAL"
    )

    update_dedicated_alb_waf_web_acls()

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    service_instance = clean_db.session.get(
        DedicatedALB,
        dedicated_alb_id,
    )

    assert service_instance.dedicated_waf_web_acl_arn == generate_fake_waf_web_acl_arn(
        dedicated_alb.dedicated_waf_web_acl_name
    )
    assert service_instance.dedicated_waf_web_acl_id == generate_fake_waf_web_acl_id(
        dedicated_alb.dedicated_waf_web_acl_name
    )
    assert service_instance.dedicated_waf_web_acl_name == "1234-dedicated-waf"
    assert service_instance.dedicated_waf_associated == True


def test_associate_dedicated_alb_has_no_waf_web_acl(
    clean_db, dedicated_alb_id, dedicated_alb, wafv2_govcloud
):
    update_dedicated_alb_waf_web_acls()

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


def test_associate_dedicated_alb_does_not_update_waf_web_acls(
    clean_db,
    dedicated_alb_id,
    dedicated_alb,
    wafv2_govcloud,
):
    dedicated_alb.dedicated_waf_web_acl_name = "1234-dedicated-waf"
    dedicated_alb.dedicated_waf_web_acl_arn = generate_fake_waf_web_acl_arn(
        dedicated_alb.dedicated_waf_web_acl_name
    )
    dedicated_alb.dedicated_waf_web_acl_id = generate_fake_waf_web_acl_id(
        dedicated_alb.dedicated_waf_web_acl_name
    )
    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    wafv2_govcloud.expect_get_web_acl_for_resource(
        dedicated_alb.alb_arn, dedicated_alb.dedicated_waf_web_acl_name
    )

    update_dedicated_alb_waf_web_acls()

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()


def test_wait_for_associated_waf_web_acl_arn(
    clean_db,
    dedicated_alb,
    wafv2_govcloud,
):
    wafv2_govcloud.expect_get_web_acl_for_resource(
        dedicated_alb.alb_arn, "different-waf"
    )
    wafv2_govcloud.expect_get_web_acl_for_resource(
        dedicated_alb.alb_arn, "1234-dedicated-waf"
    )

    wait_for_associated_waf_web_acl_arn(
        dedicated_alb.alb_arn, generate_fake_waf_web_acl_arn("1234-dedicated-waf")
    )

    wafv2_govcloud.assert_no_pending_responses()


def test_wait_for_associated_waf_web_acl_arn_gives_up(
    clean_db,
    dedicated_alb,
    wafv2_govcloud,
):
    for i in range(10):
        wafv2_govcloud.expect_get_web_acl_for_resource(
            dedicated_alb.alb_arn, "different-waf"
        )

    with pytest.raises(RuntimeError):
        wait_for_associated_waf_web_acl_arn(
            dedicated_alb.alb_arn, generate_fake_waf_web_acl_arn("1234-dedicated-waf")
        )

    wafv2_govcloud.assert_no_pending_responses()
