import uuid

from broker.aws import shield as shield_svc
from broker.lib.shield_protections import ShieldProtections
from tests.lib.fake_shield import Protection


def test_cloudfront_get_already_set_protections(shield):
    protection_id = str(uuid.uuid4())
    cloudfront_arn = "arn:aws:cloudfront::000000000:distribution/fake-arn"

    shield_protections = ShieldProtections(shield_svc)
    shield_protections.protected_cloudfront_ids = {
        cloudfront_arn: protection_id,
    }
    protections = shield_protections.get_cloudfront_protections()
    assert protections == {
        cloudfront_arn: protection_id,
    }


def test_cloudfront_get_protections(shield):
    protection_id = str(uuid.uuid4())
    cloudfront_arn = "arn:aws:cloudfront::000000000:distribution/fake-arn"
    protection: Protection = {"Id": protection_id, "ResourceArn": cloudfront_arn}
    shield.expect_list_protections([protection])

    shield_protections = ShieldProtections(shield_svc)
    protections = shield_protections.get_cloudfront_protections()
    assert protections == {
        cloudfront_arn: protection_id,
    }


def test_cloudfront_get_protections_should_refresh(shield):
    protection_id = str(uuid.uuid4())
    cloudfront_arn = "arn:aws:cloudfront::000000000:distribution/fake-arn"
    protection: Protection = {"Id": protection_id, "ResourceArn": cloudfront_arn}

    shield.expect_list_protections([protection])

    shield_protections = ShieldProtections(shield_svc)
    protections = shield_protections.get_cloudfront_protections()

    shield.expect_list_protections([protection])

    protections = shield_protections.get_cloudfront_protections(should_refresh=True)

    shield.assert_no_pending_responses()
    assert protections == {
        cloudfront_arn: protection_id,
    }


def test_cloudfront_get_protections_paged_results(shield):
    protection_id = str(uuid.uuid4())
    cloudfront_arn = "arn:aws:cloudfront::000000000:distribution/fake-arn"
    protection: Protection = {"Id": protection_id, "ResourceArn": cloudfront_arn}

    protection_id2 = str(uuid.uuid4())
    cloudfront_arn2 = "arn:aws:cloudfront::000000000:distribution/fake-arn2"
    protection2: Protection = {"Id": protection_id2, "ResourceArn": cloudfront_arn2}

    protection_id3 = str(uuid.uuid4())
    cloudfront_arn3 = "arn:aws:cloudfront::000000000:distribution/fake-arn3"
    protection3: Protection = {"Id": protection_id3, "ResourceArn": cloudfront_arn3}

    shield.expect_list_protections([protection], [protection2], [protection3])

    shield_protections = ShieldProtections(shield_svc)
    protections = shield_protections.get_cloudfront_protections()
    assert protections == {
        cloudfront_arn: protection_id,
        cloudfront_arn2: protection_id2,
        cloudfront_arn3: protection_id3,
    }
