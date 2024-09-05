#!/usr/bin/env bash

pkill -x pebble
pkill -x pebble-chall
pkill -x redis-server
pkill -f 'python3.11 -m smtpd'
pg_ctl stop
