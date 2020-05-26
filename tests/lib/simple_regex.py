import re

import pytest


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
