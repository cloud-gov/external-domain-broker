#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

# Use with `docker run --tmpfs=/db`
BASE=/db

mkdir -p $BASE/data
export PGDATA=$BASE/data
export PGHOST="$BASE/tmp"

{
  echo "Running initdb"
  initdb -A trust
  echo "listen_addresses = '127.0.0.1'" >> /db/data/postgresql.conf

  echo
  echo "Creating database and user"
  postgres --single postgres <<-EOF
    CREATE DATABASE pgdb;
    CREATE USER pguser WITH ENCRYPTED PASSWORD 'pgpasswd';
    GRANT ALL PRIVILEGES ON DATABASE pgdb TO pguser;
	EOF

  echo
  echo "Starting postgres"
} >> $BASE/logs
pg_ctl --silent --log=$BASE/logs start

exec "$@"
