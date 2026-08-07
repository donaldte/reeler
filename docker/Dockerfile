# syntax=docker/dockerfile:1
# Multi-stage Dockerfile: shared `base`, then `dev` (runserver + dev tools,
# bind-mounted source) and `prod` (gunicorn, no bind mount, static collected
# at build time) targets. Select with `docker build --target dev|prod`, or
# via docker-compose.yml / docker-compose.prod.yml.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app/.venv/bin:$PATH"

# ffmpeg: required at runtime by domain/media/ffprobe.py and (implicitly) by
# faster-whisper/PySceneDetect's decoding. libgl1/libglib2.0-0: OpenCV
# runtime dependencies even in the "headless" build.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# ---------------------------------------------------------------------------
# Development image: full dependency set (incl. dev group), source is
# expected to be bind-mounted over this at `docker compose up` time — the
# COPY here just makes the image runnable standalone (e.g. in CI) too.
# ---------------------------------------------------------------------------
FROM base AS dev

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .
RUN chmod +x docker/entrypoint.web.sh docker/entrypoint.worker.sh

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.web.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---------------------------------------------------------------------------
# Production image: no dev dependencies, static files collected at build
# time, runs as a non-root user under gunicorn.
# ---------------------------------------------------------------------------
FROM base AS prod

RUN groupadd --system reeler && useradd --system --gid reeler --create-home reeler

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV DJANGO_SETTINGS_MODULE=config.settings.prod
RUN SECRET_KEY_PLACEHOLDER=1 DJANGO_SECRET_KEY=build-time-placeholder \
    DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

RUN chmod +x docker/entrypoint.web.sh docker/entrypoint.worker.sh && chown -R reeler:reeler /app
USER reeler

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.web.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
