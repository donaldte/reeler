# Reeler

**Reeler** is an open-source, local-first AI platform that turns a long
video into a short, engaging clip for YouTube Shorts, TikTok, or Instagram
Reels — transcription, scene detection, and highlight extraction all run on
free and open-source AI models by default.

> **Status:** early / phase 1. The upload → analysis pipeline (transcript,
> scenes, AI-suggested highlights/title/description/hashtags) is real and
> working end to end. Automatic rendering/export of the final short video,
> stock media search, and AI image generation are designed-for but not yet
> implemented — see [docs/roadmap.md](docs/roadmap.md).

## What it does today

1. Upload a video.
2. Reeler extracts metadata (ffprobe), transcribes it (faster-whisper,
   local), detects scene boundaries (PySceneDetect), and asks a local LLM
   (Ollama by default) to summarize it and rank the most compelling
   moments.
3. You get a full analysis report: duration/resolution/fps/audio,
   timestamped transcript, detected scenes, a ranked highlight list with
   timestamps and rationale, and a suggested title/description/hashtags.

## Why local-first

Every AI capability is behind a pluggable provider interface
(`domain/ai/registry.py`). The defaults run entirely on your own machine —
no API keys, no per-video cost — with hosted providers (OpenRouter today)
available as a drop-in swap via environment variables. See
[docs/ai_pipeline.md](docs/ai_pipeline.md).

## Quick start

```bash
git clone <your-fork-url> reeler && cd reeler
./scripts/bootstrap.sh   # .env, uv sync, Tailwind CLI + build, pre-commit hooks
make up                  # postgres, redis, ollama, web, worker
make migrate
make ollama-pull         # pulls the default local LLM model (~2GB)
make superuser
```

Then open <http://localhost:8000>. Full walkthrough:
[docs/quickstart.md](docs/quickstart.md).

## Tech stack

Django + Django REST Framework · PostgreSQL · Redis · Celery · Docker
Compose · [uv](https://docs.astral.sh/uv/) · Tailwind CSS (standalone CLI,
no Node) · HTMX + Alpine.js · FFmpeg · OpenCV · faster-whisper ·
PySceneDetect · Ollama / OpenRouter.

## Documentation

| Doc | What's in it |
|---|---|
| [Quick start](docs/quickstart.md) | Get a working local instance running |
| [Installation](docs/installation.md) | Detailed setup, all environments |
| [Architecture](docs/architecture.md) | Layering, apps, data model, task graph |
| [AI pipeline](docs/ai_pipeline.md) | Providers, prompts, how to add a new model |
| [API](docs/api.md) | REST API reference (Swagger UI at `/api/schema/swagger-ui/`) |
| [Docker](docs/docker.md) | Dev vs. prod images, Compose services |
| [Deployment](docs/deployment.md) | Running Reeler in production |
| [Development](docs/development.md) | Local dev workflow, testing, tooling |
| [Coding standards](docs/coding_standards.md) | Style, typing, commit conventions |
| [Contributing](CONTRIBUTING.md) | How to propose changes |
| [Roadmap](docs/roadmap.md) | Where the project is headed |
| [Backlog](docs/backlog.md) | Concrete, unclaimed feature ideas |

## License

[GNU AGPL-3.0](LICENSE) — see [docs/adr/0001-license-choice.md](docs/adr/0001-license-choice.md)
for why.
