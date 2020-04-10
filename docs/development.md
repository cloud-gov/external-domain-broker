# Development

## Running Tests

Run tests via the `./scripts/test` script.  This uses the `dev` stage of the
Dockerfile, to ensure we're as close to parity with prod as possible.

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
