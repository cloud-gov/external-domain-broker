import pytest
from openbrokerapi import errors

from broker.validators import ErrorResponseConfig


@pytest.mark.parametrize("input", ["foo", 400, ["asdf", "qwer"]])
def test_must_be_dict(input):
    with pytest.raises(errors.ErrBadRequest):
        ErrorResponseConfig(input).validate()


@pytest.mark.parametrize("path", ["foo", "401", "202", "0404", 400, ["asdf", "qwer"]])
def test_keys_must_be_valid_strings(path):
    with pytest.raises(errors.ErrBadRequest):
        ErrorResponseConfig({400: path}).validate()


@pytest.mark.parametrize("path", ["", None, 400, ["asdf", "qwer"]])
def test_values_must_be_strings(path):
    with pytest.raises(errors.ErrBadRequest):
        ErrorResponseConfig({"400": path}).validate()


@pytest.mark.parametrize("path", [" /", "./", "index.html"])
def test_paths_must_be_absolute(path):
    with pytest.raises(errors.ErrBadRequest):
        ErrorResponseConfig({"400": path}).validate()
