# Development Guide

## Everyday commands

```bash
make up              # start the dev stack
make logs             # tail web logs
make worker-logs       # tail worker logs
make shell              # Django shell inside the web container
make manage ARGS="..."   # any manage.py command
make migrate
make makemigrations
make test              # pytest with coverage
make lint               # ruff check
make format               # ruff format + fix
make typecheck              # mypy
make check                    # lint + typecheck + test — what CI runs
```

## Running tests

```bash
uv run pytest                                  # everything
uv run pytest domain                            # domain/ only (no DB needed)
uv run pytest apps/videos                         # one app
uv run pytest -k test_full_pipeline                # by name
uv run pytest --cov-report=html && open htmlcov/index.html
```

Tests need a real Postgres reachable via `DATABASE_URL` — `make test` runs
inside the `web` container against the `db` service. Running `uv run pytest`
on your host requires a local Postgres (or point `DATABASE_URL` at the
Dockerized one with the port published, which `docker-compose.yml` does by
default: `postgres://reeler:reeler@localhost:5432/reeler_test` — create
that database once with `createdb reeler_test` or let `pytest-django`
create it for you).

## Frontend / Tailwind

No Node/npm — a standalone Tailwind CLI binary. `make tailwind-install`
downloads it into `bin/tailwindcss` (gitignored); `make tailwind-build` does
a one-shot minified build to `static/css/output.css` (also gitignored —
regenerate it, don't commit it); `make tailwind-watch` rebuilds on save
while developing.

## Adding a Django app

Follow the existing shape (`apps/videos` is the most complete example):
`models.py`, `admin.py`, `apps.py` (explicit `AppConfig` with a `label`),
`tasks.py` if it has pipeline work, `api/{serializers,views,urls}.py`,
`templates/<app>/`, `tests/`. Register it in `LOCAL_APPS` in
`config/settings/base.py`, then `make makemigrations`.

## Debugging the pipeline locally

Set `CELERY_TASK_ALWAYS_EAGER=true` in `.env` to run the whole pipeline
synchronously in the `web` process (no worker needed) — convenient for
stepping through with a debugger, but see the caveat in
[docs/ai_pipeline.md](ai_pipeline.md#operational-notes) about error
propagation before using it for anything beyond a quick check.

## Before opening a PR

`make check`, then see [CONTRIBUTING.md](../CONTRIBUTING.md) and
[docs/coding_standards.md](coding_standards.md).
