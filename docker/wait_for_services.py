#!/usr/bin/env python
"""Blocks until Postgres (and, if requested, Redis) accept connections.

Used by docker/entrypoint.web.sh and docker/entrypoint.worker.sh so neither
container races the `db`/`redis` services during `docker compose up`.
Usage: python wait_for_services.py [--redis]
"""

import sys
import time

import environ

env = environ.Env()
TIMEOUT_SECONDS = 60
POLL_INTERVAL_SECONDS = 1


def wait_for_postgres() -> None:
    import psycopg

    db = env.db_url("DATABASE_URL", default="postgres://reeler:reeler@db:5432/reeler")
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            psycopg.connect(
                host=db["HOST"],
                port=db["PORT"],
                dbname=db["NAME"],
                user=db["USER"],
                password=db["PASSWORD"],
                connect_timeout=2,
            ).close()
            print("Postgres is ready.")
            return
        except Exception:
            time.sleep(POLL_INTERVAL_SECONDS)
    sys.exit("Timed out waiting for Postgres.")


def wait_for_redis() -> None:
    import redis

    url = env.str("CELERY_BROKER_URL", default="redis://redis:6379/0")
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            redis.from_url(url, socket_connect_timeout=2).ping()
            print("Redis is ready.")
            return
        except Exception:
            time.sleep(POLL_INTERVAL_SECONDS)
    sys.exit("Timed out waiting for Redis.")


if __name__ == "__main__":
    wait_for_postgres()
    if "--redis" in sys.argv:
        wait_for_redis()
