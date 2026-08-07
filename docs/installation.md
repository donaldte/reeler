# Installation

For the fastest path to a running instance, see [Quick Start](quickstart.md)
instead — this doc covers the details and non-Docker options.

## Docker (recommended)

Covered in full in [Quick Start](quickstart.md) and [Docker guide](docker.md).
TL;DR: `./scripts/bootstrap.sh && make up && make migrate && make ollama-pull`.

## Running without Docker

Requires locally installed: Python 3.12+, `uv`, PostgreSQL 16+, Redis 7+,
FFmpeg, and (optionally) Ollama.

```bash
uv sync
cp .env.example .env
# Edit .env: point DATABASE_URL / CELERY_BROKER_URL / CELERY_RESULT_BACKEND
# at your local Postgres/Redis instead of the `db`/`redis` service names.

uv run python manage.py migrate
uv run python manage.py createsuperuser

# Terminal 1
uv run python manage.py runserver

# Terminal 2
uv run celery -A config worker -l info

# Terminal 3 (if using the local LLM provider)
ollama serve
ollama pull qwen2.5:3b
```

Build the frontend assets once (or `make tailwind-watch` while developing):

```bash
./scripts/install_tailwind.sh
make tailwind-build
```

## Configuration reference

Every setting is documented inline in `.env.example` and read via
`django-environ` in `config/settings/base.py`. Key groups:

- **Django**: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`
- **Database**: `DATABASE_URL`
- **Celery**: `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`,
  `CELERY_TASK_ALWAYS_EAGER`
- **AI providers**: `AI_STT_PROVIDER`, `AI_LLM_PROVIDER`, and each
  provider's own keys — see [AI pipeline](ai_pipeline.md)
- **Scene detection**: `SCENE_DETECTION_THRESHOLD`,
  `SCENE_DETECTION_MIN_SCENE_LEN_SECONDS`

## Verifying your install

```bash
make check   # ruff + mypy + pytest
```

or, without Docker: `uv run pytest`.
