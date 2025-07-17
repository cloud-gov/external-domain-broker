from tests.lib.client import (
    app,
    clean_db,
    client,
    no_context_clean_db,
    no_context_app,
)  # noqa 401
from tests.lib.fake_alb import alb  # noqa F401
from tests.lib.fake_cloudfront import cloudfront  # noqa F401
from tests.lib.fake_iam import iam_commercial, iam_govcloud  # noqa F401
from tests.lib.fake_route53 import route53  # noqa F401
from tests.lib.fake_wafv2 import wafv2_commercial, wafv2_govcloud  # noqa F401
from tests.lib.fake_shield import shield  # noqa F401
from tests.lib.fake_cloudwatch import cloudwatch_commercial  # noqa F401
from tests.lib.fake_sns import sns_commercial  # noqa F401
from tests.lib.simple_regex import simple_regex  # noqa F401
from tests.lib.cdn.instances import (
    unmigrated_cdn_service_instance_operation_id,
    unmigrated_cdn_dedicated_waf_service_instance_operation_id,
)  # noqa F401
from tests.lib.dns import dns  # noqa 401
from tests.lib.tasks import tasks  # noqa 401
from tests.lib.cf import (
    access_token,
    access_token_response,
    mock_with_uaa_auth,
    space_guid,
    organization_guid,
    mocked_cf_api,
)  # noqa 41
from tests.lib.identifiers import (
    service_instance_id,
    operation_id,
    new_cert_id,
    current_cert_id,
    cloudfront_distribution_arn,
    protection_id,
    dedicated_waf_web_acl_arn,
    cache_policy_id,
    origin_request_policy_id,
    dedicated_alb_id,
    dedicated_alb_arn,
    waf_web_acl_arn,
)  # noqa 41


def pytest_configure(config):
    config.addinivalue_line("markers", "focus: Only run this test.")


def pytest_collection_modifyitems(items, config):
    """
    Focus on tests marked focus, if any.  Run all
    otherwise.
    """

    selected_items = []
    deselected_items = []

    focused = False

    for item in items:
        if item.get_closest_marker("focus"):
            focused = True
            selected_items.append(item)
        else:
            deselected_items.append(item)

    if focused:
        print("\nOnly running @pytest.mark.focus tests")
        config.hook.pytest_deselected(items=deselected_items)
        items[:] = selected_items
