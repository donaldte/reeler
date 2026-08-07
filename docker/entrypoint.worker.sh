#!/usr/bin/env bash
set -euo pipefail

python docker/wait_for_services.py --redis

echo "Starting: $*"
exec "$@"
