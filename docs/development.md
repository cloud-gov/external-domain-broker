# Development

## Open Service Broker API

We're using https://github.com/eruvanos/openbrokerapi, and we used
https://github.com/eruvanos/openbrokerapi-skeleton to start the project.

## Running Tests

Run tests via the `./scripts/dev tests` script. This uses the `dev` stage of
the Dockerfile, to ensure we're as close to parity with prod as possible.

### In Production

Runs release image

### Local Tests

1. Run `./script/dev watch-tests`
1. which builds the container using `dev` stage
1. watches the tests inside it.

### Concourse Tests

1. Build `dev` image
1. Run unit tests inside it
1. Deploy shared DB in dev (fast, but old psql version)
1. Deploy app to dev
1. Run acceptance tests inside `dev` image against `HOST:PORT` of app
1. Delete DB and app?

## Adding Packages

We're using [pip-tools](https://github.com/jazzband/pip-tools) for managing
packages. It provides the same strong locking semantics that Pipenv provides,
but it's actually maintained.

To add a new package, edit the `pip-tools/requirements.in` (for production
requirements) or `pip-tools/dev-requirements.in` (for development requirements)
files and run:

```console
$ ./scripts/dev update-requirements
Compiling requirements.txt
Compiling dev-requirements.txt
```

## Code Style

We use [Black](https://github.com/psf/black) to format our code. Please do
the same.

## Architecture

## WIP Notes and Useful Links

- https://acme-python.readthedocs.io/en/stable/index.html
- http://www.gilesthomas.com/2018/11/python-code-to-generate-lets-encrypt-certificates/ (outdated, but still useful)
- https://github.com/eruvanos/openbrokerapi-skeleton - where we started
- https://github.com/eruvanos/openbrokerapi
- https://openbrokerapi.readthedocs.io/en/latest/openbrokerapi.html#module-openbrokerapi.api
- https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md
- https://github.com/openservicebrokerapi/servicebroker/blob/v2.14/spec.md#polling-last-operation-for-service-bindings
- https://github.com/openservicebrokerapi/servicebroker/blob/master/profile.md#service-metadata
- https://docs.cloudfoundry.org/services/managing-service-brokers.html
- https://docs.cloudfoundry.org/services/access-control.html#enable-access
