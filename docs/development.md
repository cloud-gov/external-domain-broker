# Development

## Open Service Broker API

We're using https://github.com/eruvanos/openbrokerapi, and we used
https://github.com/eruvanos/openbrokerapi-skeleton to start the project.

## Running Tests

Run tests via the `./dev tests` script. This uses the `dev` stage of
the Dockerfile, to ensure we're as close to parity with prod as possible.

## Generate a DB Migration File

We're using [flask-migrate](https://flask-migrate.readthedocs.io/en/latest/)
for migrations.  flask-migrate can auto-generate a migration file by looking
at what's currently in the database, what's defined in our
[models](/broker/models.py), and generating a migration file that would
bridge the gap.  However, our `tmp/dev.sqlite` database is automatically created
and destroyed with each test run.  In order to generate a migration, you
should first create the `tmp/dev.sqlite` database:

``` console
$ ./dev run flask db upgrade
```

...and then generate the migration file:

``` console
$ ./dev run flask db migrate -m "Change description"
```

## Adding Packages

We're using [pip-tools](https://github.com/jazzband/pip-tools) for managing
packages. It provides the same strong locking semantics that Pipenv provides,
but it's actually maintained.

To add a new package, edit the `pip-tools/requirements.in` (for production
requirements) or `pip-tools/dev-requirements.in` (for development requirements)
files and run:

```console
$ ./dev update-requirements
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
