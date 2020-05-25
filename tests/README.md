# Testing

## General development workflow

In one window, run the tests continually via the `./dev watch-tests` script.
This runs the test watcher in a Docker container, and mounts your local
directory over the container's application codebase.

In another, simply edit your files as normal.  The test watcher should pick up
any changes when you save files and run the tests again.

### Test focus

If you'd like the test runner to only run the test(s) you care about, annotate
them with the `focus` mark like such:

``` python
@pytest.mark.focus
def test_provision_creates_LE_user(client, tasks, pebble):
    ...
```

This is enabled in the `tests/conftest.py` file, and [described
here](https://superorbit.al/journal/focusing-on-pytest/).

In order to ensure you don't commit tests that include the `focus` marker, we
suggest you include the following git `pre-commit.sh` hook:

``` bash
#!/usr/bin/env bash

# This detects pytest files that include the focus marker.
# https://superorbit.al/journal/focusing-on-pytest/

if grep -RFl --include "test_*.py" pytest.mark.focus > /dev/null 2>&1; then
  echo "Error: The following pytest files still have a pytest.mark.focus annotation:"
  echo
  grep -RFl --include "test_*.py" pytest.mark.focus
  exit 2
fi
```

## Test Libraries

All of our fixtures, factories and general test helpers are in [the
`/tests/lib` directory](/tests/lib).  Please familiarize yourself with these,
as they're used throughout.

## Test Struture

We have both unit and integration tests.  My approach has been to focus on
integration tests, and only drop down to unit tests for functionality that's
difficult to test at a higher level.  As a result, we have many more
integration tests.

## Mocking

We try to mock as little as possible, and to push our mocks as far out as
possible.  For example, we don't mock our use of the acme package.  Instead, we
run [pebble](https://github.com/letsencrypt/pebble) in our Docker container,
and point acme at that.  Similarly, we use the [pebble challenge test
server](https://github.com/letsencrypt/pebble/tree/master/cmd/pebble-challtestsrv)
to control what pebble sees when it makes DNS queries.

Sometimes, we're forced to use local mocks.  For example, we use the [boto3
Stubber](https://botocore.amazonaws.com/v1/documentation/api/latest/reference/stubber.html)
mocking tool to mock out AWS Route53 and CloudFormation calls.  We'd
have liked to have used [LocalStack](https://github.com/localstack/localstack),
but it doesn't support these services.
