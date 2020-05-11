import re
import pytest


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


class SimpleRegex:
    """
    Helper for simplifying regex assertions

    Use like such:

    assert "some\nmultiline\nstring" == simple_regex(r'some multiline')
    """

    def __init__(self, pattern):
        pattern = pattern.replace(" ", "\\s")
        self._regex = re.compile(pattern, re.MULTILINE | re.DOTALL)

    def __eq__(self, actual):
        return bool(self._regex.search(actual))

    def __repr__(self):
        return self._regex.pattern


@pytest.fixture
def simple_regex():
    def _simple_regex(pattern):
        return SimpleRegex(pattern)

    return _simple_regex
