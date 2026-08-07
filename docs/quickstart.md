# Quick Start

Gets you from a fresh clone to analyzing your first video.

## Prerequisites

- Docker + Docker Compose v2 (`docker compose version`)
- `git`
- ~4GB free disk (Ollama model + Whisper model caches)

You do **not** need Python, ffmpeg, PostgreSQL, or Redis installed on your
host — they all run inside containers.

## 1. Clone and bootstrap

```bash
git clone <your-fork-url> reeler
cd reeler
./scripts/bootstrap.sh
```

This copies `.env.example` to `.env`, installs Python dependencies with
`uv`, downloads the standalone Tailwind CLI and builds `static/css/output.css`,
and installs pre-commit hooks. Open `.env` and adjust anything you need to
(defaults work out of the box for local dev).

## 2. Start the stack

```bash
make up
```

Starts `db` (Postgres), `redis`, `ollama`, `web` (Django dev server on
`:8000`), and `worker` (Celery). First boot pulls/builds images, so it can
take a few minutes.

## 3. Apply migrations and pull the default model

```bash
make migrate
make ollama-pull    # pulls qwen2.5:3b (~2GB) — only needed once
```

## 4. Create a login

```bash
make superuser
```

## 5. Upload a video

Visit <http://localhost:8000>, log in, and upload a short video (MP4, MOV,
MKV, WebM, or AVI). You'll be redirected to its analysis page, which polls
for progress and shows the full report once complete: transcript, detected
scenes, and AI-suggested title/description/hashtags/highlights.

First run will be slower than usual: faster-whisper downloads its model
weights on first use (cached afterward in the `whisper_cache` volume), and
Ollama loads the model into memory on first request.

## Troubleshooting

- **Upload stuck on "Extracting metadata"**: check `make logs` — this step
  needs `ffmpeg`/`ffprobe`, which is baked into the `web`/`worker` images;
  if you're running outside Docker, install ffmpeg yourself.
- **Stuck on "Analyzing"**: check `make worker-logs`. Most often the
  Ollama model hasn't finished loading yet (first request after container
  start is slow), or `make ollama-pull` was never run.
- **"OPENROUTER_API_KEY is required" error**: you set
  `AI_LLM_PROVIDER=openrouter` without setting the key in `.env`.

## What's next

- [Installation guide](installation.md) for non-Docker / production setups.
- [AI pipeline](ai_pipeline.md) to swap providers or tune models.
- [Development guide](development.md) for running tests and the dev loop.
- [API docs](api.md) if you want to drive Reeler programmatically.
