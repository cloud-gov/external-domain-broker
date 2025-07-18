import json
import pytest

from broker.commands.tags import add_dedicated_alb_tags
from broker.extensions import config
from broker.models import DedicatedALB
from tests.lib import factories
from tests.lib.tags import sort_instance_tags


@pytest.fixture
def dedicated_alb(
    clean_db, dedicated_alb_id, dedicated_alb_arn, organization_guid, waf_web_acl_arn
):
    dedicated_alb = factories.DedicatedALBFactory.create(
        id=dedicated_alb_id,
        alb_arn=dedicated_alb_arn,
        dedicated_org=organization_guid,
        dedicated_waf_web_acl_arn=waf_web_acl_arn,
    )

    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    return dedicated_alb


def test_add_dedicated_alb_tags(
    clean_db,
    dedicated_alb,
    dedicated_alb_id,
    access_token,
    mock_with_uaa_auth,
    organization_guid,
    wafv2_govcloud,
):

    response = json.dumps({"guid": organization_guid, "name": "org-1234"})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/organizations/{organization_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert not dedicated_alb.tags

    expected_tags = [
        {"Key": "client", "Value": "Cloud Foundry"},
        {"Key": "broker", "Value": "External domain broker"},
        {"Key": "environment", "Value": config.FLASK_ENV},
        {"Key": "Organization GUID", "Value": organization_guid},
        {"Key": "Organization name", "Value": "org-1234"},
    ]

    wafv2_govcloud.expect_tag_resource(
        dedicated_alb.dedicated_waf_web_acl_arn, expected_tags
    )

    add_dedicated_alb_tags()

    wafv2_govcloud.assert_no_pending_responses()

    clean_db.session.expunge_all()

    dedicated_alb = clean_db.session.get(DedicatedALB, dedicated_alb_id)

    assert sort_instance_tags(dedicated_alb.tags) == sort_instance_tags(expected_tags)


def test_add_dedicated_alb_tags_does_nothing_existing_tags(
    clean_db,
    dedicated_alb,
    wafv2_govcloud,
):

    dedicated_alb.tags = [{"foo": "bar"}]
    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    add_dedicated_alb_tags()

    wafv2_govcloud.assert_no_pending_responses()


def test_add_dedicated_alb_tags_requires_waf_arn(
    clean_db,
    dedicated_alb,
    wafv2_govcloud,
    organization_guid,
    mock_with_uaa_auth,
    access_token,
):
    dedicated_alb.dedicated_waf_web_acl_arn = None
    clean_db.session.add(dedicated_alb)
    clean_db.session.commit()

    response = json.dumps({"guid": organization_guid, "name": "org-1234"})
    mock_with_uaa_auth.get(
        f"http://mock.cf/v3/organizations/{organization_guid}",
        text=response,
        request_headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    add_dedicated_alb_tags()

    wafv2_govcloud.assert_no_pending_responses()
