import pytest
from openbrokerapi import errors

from broker.validators import HeaderList


def test_empty_headers():
    with pytest.raises(errors.ErrBadRequest):
        HeaderList([""]).validate()


def test_valid_headers():
    HeaderList(["foo", "foo-bar", "###", "*!"]).validate()
    HeaderList([]).validate()
