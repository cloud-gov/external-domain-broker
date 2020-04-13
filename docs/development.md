# Development

## Running Tests

Run tests via the `./scripts/test` script.  This uses the `dev` stage of the
Dockerfile, to ensure we're as close to parity with prod as possible.

### In Production

Runs release image

### Local Tests

1. Run `./script/test watch`
1. which composes `docker-compose.yml` and `docker-compose-tests.yml`
1. `docker-compose-tests.yml` runs extra container using `dev` stage
1. watches the tests inside it.
1. Some of those tests run units against the local FS.
1. Some run acceptance against `HOST:PORT`
1. `<ctrl-c>` kills compose and DB, etc.

### Concourse Tests

1. Build `dev` image
1. Run unit tests inside it
1. Deploy shared DB in dev (fast, but old psql version)
1. Deploy app to dev
1. Run acceptance tests inside `dev` image against `HOST:PORT` of app
1. Delete DB and app?

## Adding Packages

We're using [pip-tools](https://github.com/jazzband/pip-tools) for managing
packages.  It provides the same strong locking semantics that Pipenv provides,
but it's actually maintained.

To add a new package, edit the `pip-tools/requirements.in` (for production
requirements) or `pip-tools/dev-requirements.in` (for development requirements)
files and run:

``` console
$ ./scripts/update-requirements-txt
Building the temporary docker image
Compiling requirements.txt
Compiling dev-requirements.txt
```

## Code Style

We use [Black](https://github.com/psf/black) to format our code.  Please do the same.

We've provided a `scripts/black` script, which runs black via docker. We've
also included a `.lvimrc`, which will configure ALE and black for vim using
localvimrc (both plugins are required).

## Architecture
