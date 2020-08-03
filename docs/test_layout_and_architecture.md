# Test layout and architecture

The majority of the testing lives in the `integration` section. These tests are centered around
happy-path tests that walk through pipelines, using mocks to replace AWS, using `pebble` as
a stand-in for Lets Encrypt, and using a disposable local postgres for persistence.

This has some downsides:
- mocks for AWS are only as accurate as our understanding of AWS
- pebble + postgres mean it's pretty impractical to run tests locally without using the supplied docker container
- pebble + postgres make it relatively slow to run all of the tests together

Integration tests are split pretty cleanly between ALB and CDN service options, each having:
- provisioning tests
- update tests
- renewal tests
- deprovisioning tests

Each of the test sections has a happy-path pipeline (although the update's pipeline is called by
the provision pipeline), as well as a handful of smaller tests mostly to cover input validation.
