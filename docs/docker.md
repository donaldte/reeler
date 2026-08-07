# Docker Guide

## Images

`docker/Dockerfile` is a multi-stage build sharing a `base` stage (Python
3.12-slim + ffmpeg + OpenCV runtime libs + `uv`), with two targets:

| Target | Used by | Characteristics |
|---|---|---|
| `dev` | `docker-compose.yml` (default) | Full dependency set incl. dev tools; source bind-mounted over the image; `runserver` |
| `prod` | `docker-compose.prod.yml` overlay | No dev dependencies; source baked in (no bind mount); static collected at build time; runs as non-root `reeler` user; gunicorn |

Build a specific target directly: `docker build --target dev -f docker/Dockerfile .`

## Services (`docker-compose.yml`)

| Service | Role |
|---|---|
| `db` | PostgreSQL 16 |
| `redis` | Celery broker + result backend |
| `ollama` | Local LLM server (default `AI_LLM_PROVIDER`) |
| `web` | Django (dev server in dev, gunicorn in prod) |
| `worker` | Celery worker running the analysis pipeline |

`docker-compose.prod.yml` is an **overlay**, not a standalone file — always
run it combined with the base file:
`docker compose -f docker-compose.yml -f docker-compose.prod.yml ...`
(or `make`-wrap this if you deploy this way often). It switches `web`/
`worker` to the `prod` build target, drops bind mounts and dev-only host
port bindings on internal services, and adds an `nginx` service serving
`/static/`/`/media/` directly and reverse-proxying everything else to `web`.

## Entrypoints

`docker/entrypoint.web.sh` waits for Postgres
(`docker/wait_for_services.py`), runs migrations, collects static files in
prod, then execs the container's `CMD`. `docker/entrypoint.worker.sh` waits
for Postgres **and** Redis before execing the Celery worker command. Both
are set as each stage's `ENTRYPOINT` in the Dockerfile; `docker-compose.yml`
overrides `worker`'s entrypoint/command since it shares the `dev`/`prod`
image with `web` but needs a different startup sequence.

## Volumes

| Volume | Purpose |
|---|---|
| `postgres_data` | Database files |
| `media_files` | Uploaded videos (shared read/write between `web` and `worker`) |
| `ollama_data` | Downloaded Ollama models |
| `whisper_cache` | HuggingFace cache — avoids re-downloading the Whisper model every worker restart |
| `staticfiles` (prod only) | Collected static assets, served by nginx |

## Common tasks

```bash
make up                 # docker compose up -d
make build                # rebuild images after a Dockerfile/pyproject change
make logs / worker-logs      # tail logs
make shell                     # Django shell in the web container
make manage ARGS="..."           # any manage.py command
make ollama-pull                    # pull the configured Ollama model (once)
```

## Rebuilding after a dependency change

```bash
make build && make up
```

`uv.lock` is committed, so `uv sync --frozen` inside the image build is
reproducible — always run `uv add <package>` (which updates `uv.lock`)
rather than editing `pyproject.toml`'s dependency list by hand.
