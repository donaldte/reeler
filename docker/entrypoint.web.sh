#!/usr/bin/env bash
set -euo pipefail

python docker/wait_for_services.py

echo "Applying migrations..."
python manage.py migrate --noinput

if [ "${DJANGO_SETTINGS_MODULE:-}" = "config.settings.prod" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

echo "Starting: $*"
exec "$@"
