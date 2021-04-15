from openbrokerapi import errors
import pytest

from broker.validators import Hostname


@pytest.mark.parametrize(
    "hostname",
    [
        "a.co",
        "foo.example.com",
        "several.layers.deep.example.gov.but-wait.there-s-more.gov",
    ],
)
def test_basic_hostname(hostname):
    # we're just making sure we don't raise an exception here
    Hostname(hostname).validate()


def test_bad_because_of_protocol():
    with pytest.raises(errors.ErrBadRequest):
        Hostname("https://foo.example.gov").validate()


@pytest.mark.parametrize(
    "hostname",
    [
        "-example.com",
        "example-.com",
        "example.-com",
        "example.com-",
        "example.com-.gov",
        "example.-com.gov",
        "example.com.-gov",
        "example.com.gov-",
        "example.-",
    ],
)
def test_bad_dashes(hostname):
    with pytest.raises(errors.ErrBadRequest):
        Hostname(hostname).validate()


@pytest.mark.parametrize("hostname", [".c", "a.c", "example.a"])
def test_bad_tld_lengths(hostname):
    with pytest.raises(errors.ErrBadRequest):
        Hostname(hostname).validate()


def test_bad_octet_lengths():
    hostname = ".com"
    for i in range(63):
        hostname = "a" + hostname
        Hostname(hostname).validate()
        # test middle-node, too
        Hostname(f"www.{hostname}.foo").validate()
    hostname = "a" + hostname
    with pytest.raises(errors.ErrBadRequest):
        Hostname(hostname).validate()


def test_bad_total_length():
    hostname = 62 * "aaa." + "aaaaa"
    assert len(hostname) == 253
    Hostname(hostname).validate()

    hostname = "a" + hostname
    assert len(hostname) == 254
    with pytest.raises(errors.ErrBadRequest):
        Hostname(hostname).validate()
