# Guide for local development

## `dev` script

The [`dev`](./dev) script contains a number of useful commands for local development and testing:

- `new-migration` - Create a new [database migration file](https://alembic.sqlalchemy.org/en/latest/tutorial.html#create-a-migration-script)
- `run <command>` - Run arbitrary command in the test container
- `serve` - Run the application, binding to local port 8000
- `shell` - Start an interactive bash shell in the tests container
- `tests` - Run the test suite once
- `upgrade-requirements` - Generate the `pip-tools/*requirements.txt` files from `pip-tools/*requirements.in`
- `watch-tests` - Continually watch for file changes and run tests

You can run these commands like so:

```shell
./dev tests
```

## Running and debugging tests

### Prerequisites

- Python 3.8 + `pip`

### Install dependencies

```shell
python -m venv venv # Create virtual environment
source ./venv/bin/activate # Activate virtual environment
pip install -r requirements.txt # Install requirements
pip install -r pip-tools/dev-requirements.txt # Install requirements
```

### Start up local PostgreSQL database

Start up a PostgreSQL service that will be exposed on `localhost:5432`, which is what is expected by the test suite configuration:

```shell
cd docker
docker-compose up -d  # Start up services in docker-compose.yml
```

The `-d` flag is optional. If you omit, then logs from the PostgreSQL container will stream to your terminal, which may be helpful in debugging tests.

### Run + debug tests in VScode

Follow the [VScode documentation to discover, to run, and to debug the tests in VScode](https://code.visualstudio.com/docs/python/testing).