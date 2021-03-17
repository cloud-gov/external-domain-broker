import openbrokerapi
import pytest

from broker.validators import CNAME


def test_one_layer_of_cnames(dns):
    dns.add_cname("_acme-challenge.foo.example.gov")
    # we're just making sure we don't raise an exception here
    CNAME(["foo.example.gov"]).validate()


def test_two_layers_of_cnames(dns):
    dns.add_cname(
        "_acme-challenge.foo.example.gov", target="_acme-challenge.bar.example.gov"
    )
    dns.add_cname(
        "_acme-challenge.bar.example.gov",
        target="_acme-challenge.foo.example.gov.domains.cloud.test",
    )
    # we're just making sure we don't raise an exception here
    CNAME(["foo.example.gov"]).validate()


def test_three_layers_of_cnames(dns):
    dns.add_cname(
        "_acme-challenge.foo.example.gov", target="_acme-challenge.bar.example.gov"
    )
    dns.add_cname(
        "_acme-challenge.bar.example.gov", target="_acme-challenge.baz.example.gov"
    )
    dns.add_cname(
        "_acme-challenge.baz.example.gov",
        target="_acme-challenge.foo.example.gov.domains.cloud.test",
    )
    # we're just making sure we don't raise an exception here
    CNAME(["foo.example.gov"]).validate()


def test_detects_looping_cnames(dns):
    dns.add_cname(
        "_acme-challenge.foo.example.gov", target="_acme-challenge.bar.example.gov"
    )
    dns.add_cname(
        "_acme-challenge.bar.example.gov", target="_acme-challenge.foo.example.gov"
    )
    # we're just making sure we don't raise an exception here
    with pytest.raises(
        openbrokerapi.errors.ErrBadRequest,
        match=r"_acme-challenge.foo.example.gov points to itself. Resolution chain: \['_acme-challenge.foo.example.gov', '_acme-challenge.bar.example.gov'\]",
    ):
        CNAME(["foo.example.gov"]).validate()
