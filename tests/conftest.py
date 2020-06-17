from tests.lib.client import app, clean_db, client  # noqa 401
from tests.lib.fake_alb import alb  # noqa F401
from tests.lib.fake_cloudfront import cloudfront  # noqa F401
from tests.lib.fake_iam import iam_commercial, iam_govcloud  # noqa F401
from tests.lib.fake_route53 import route53  # noqa F401
from tests.lib.simple_regex import simple_regex  # noqa F401
from tests.lib.dns import dns  # noqa 401
from tests.lib.tasks import tasks  # noqa 401


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
