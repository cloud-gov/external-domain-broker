# Development

## Running Tests

Run tests via the `./scripts/test` script.

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

## Architecture
