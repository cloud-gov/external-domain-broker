import pytest
import uuid
import requests_mock

from broker.lib import cf


@pytest.fixture
def space_guid():
    return str(uuid.uuid4())


@pytest.fixture
def organization_guid():
    return str(uuid.uuid4())


def test_gets_space_name(space_guid):
    with requests_mock.Mocker() as m:
        response = """
  {
    "guid": "{space_guid}",
    "name": "foobar-space"
  }
    """
        m.get(
            f"http://mock.cf/v3/spaces/{space_guid}",
            text=response,
        )
        assert cf.get_space_name_by_guid(space_guid, "a_token") == "foobar-space"


def test_gets_org_name(organization_guid):
    with requests_mock.Mocker() as m:
        response = """
  {
    "guid": "{organization_guid}",
    "name": "org-1234"
  }
    """
        m.get(
            f"http://mock.cf/v3/organizations/{organization_guid}",
            text=response,
        )
        assert cf.get_org_name_by_guid(organization_guid, "a_token") == "org-1234"
