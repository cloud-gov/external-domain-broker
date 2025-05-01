import pytest

from openbrokerapi import errors

from broker.aws import cloudfront as real_cloudfront
from broker.lib.cdn import parse_cache_policy, parse_origin_request_policy
from broker.lib.cache_policy_manager import CachePolicyManager
from broker.lib.origin_request_policy_manager import OriginRequestPolicyManager


@pytest.fixture
def cache_policy_manager():
    return CachePolicyManager(real_cloudfront)


@pytest.fixture
def origin_request_policy_manager():
    return OriginRequestPolicyManager(real_cloudfront)


def test_parse_cache_policy_returns_none(cache_policy_manager):
    assert parse_cache_policy({}, cache_policy_manager) == None


def test_parse_cache_policy_returns_valid_cache_policy(
    cache_policy_manager, cache_policy_id, cloudfront
):
    policies = [{"id": cache_policy_id, "name": "Managed-CachingDisabled"}]
    cloudfront.expect_list_cache_policies("managed", policies)

    assert (
        parse_cache_policy(
            {"cache_policy": "Managed-CachingDisabled"}, cache_policy_manager
        )
        == cache_policy_id
    )


def test_parse_cache_policy_raises_error_invalid_cache_policy(cache_policy_manager):
    with pytest.raises(errors.ErrBadRequest):
        parse_cache_policy({"cache_policy": "FakePolicy"}, cache_policy_manager)


def test_parse_origin_request_policy_returns_none(origin_request_policy_manager):
    assert parse_origin_request_policy({}, origin_request_policy_manager) == None


def test_parse_origin_request_policy_returns_valid_origin_request_policy(
    origin_request_policy_manager, origin_request_policy_id, cloudfront
):
    policies = [{"id": origin_request_policy_id, "name": "Managed-AllViewer"}]
    cloudfront.expect_list_origin_request_policies("managed", policies)

    assert (
        parse_origin_request_policy(
            {"origin_request_policy": "Managed-AllViewer"},
            origin_request_policy_manager,
        )
        == origin_request_policy_id
    )


def test_parse_origin_request_policy_raises_error_invalid_origin_request_policy(
    origin_request_policy_manager,
):
    with pytest.raises(errors.ErrBadRequest):
        parse_origin_request_policy(
            {"origin_request_policy": "FakePolicy"}, origin_request_policy_manager
        )
