import uuid
from broker.tasks import shield as shield_tasks

# from tests.lib.fake_shield import shield as test_shield


def test_cloudfront_list_protections(shield):
    protection_id = str(uuid.uuid4())
    cloudfront_arn = "arn:aws:cloudfront::000000000:distribution/fake-arn"
    shield.expect_list_protections(protection_id, cloudfront_arn)

    protections = shield_tasks.list_cloudfront_protections()
    assert protections == {
        cloudfront_arn: protection_id,
    }
