# Development

## General development workflow

In one window, run the tests continually via the `./dev watch-tests` script.
This runs the test watcher in a Docker container, and mounts your local
directory over the container's application codebase.

In another, simply edit your files as normal.  The test watcher should pick up
any changes when you save files and run the tests again.  If you'd like it to
only run the test(s) you care about, annotate them with the `focus` mark like
such:

``` python
@pytest.mark.focus
def test_provision_creates_LE_user(client, tasks, pebble):
    ...
```

## Generate a DB Migration File

We're using [flask-migrate](https://flask-migrate.readthedocs.io/en/latest/)
for migrations.  flask-migrate can auto-generate a migration file by looking
at what's currently in the database, what's defined in our
[models](/broker/models.py), and generating a migration file that would
bridge the gap.

First ensure the `tmp/dev.sqlite` database is up to date (this also happens
when you run `./dev serve`):

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

### Open Service Broker API

We're using https://github.com/eruvanos/openbrokerapi, and we used
https://github.com/eruvanos/openbrokerapi-skeleton to start the project.

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
