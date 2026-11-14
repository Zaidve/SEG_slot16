#!/usr/bin/env bash
# Render runs this each time the site starts. Stop at the first error.
set -o errexit
cd backend

python manage.py migrate --no-input
# Safe to repeat. It also redraws article banners, because Render's disk is
# wiped whenever the free instance restarts.
python manage.py seed_data

exec gunicorn config.wsgi:application --bind "0.0.0.0:$PORT"
