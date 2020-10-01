import pytest
from broker import api


def test_parse_domains():
    assert api.parse_domain_options(dict(domains="example.com")) == ["example.com"]
    assert api.parse_domain_options(dict(domains="example.com,example.gov")) == [
        "example.com",
        "example.gov",
    ]
    assert api.parse_domain_options(dict(domains=["example.com"])) == ["example.com"]
    assert api.parse_domain_options(dict(domains=["example.com", "example.gov"])) == [
        "example.com",
        "example.gov",
    ]
    assert api.parse_domain_options(dict(domains=["eXaMpLe.cOm   "])) == ["example.com"]
