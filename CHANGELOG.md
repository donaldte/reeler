# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Initial project scaffold: modular Django apps (`accounts`, `common`,
  `videos`, `transcripts`, `scenes`, `highlights`, `ai_providers`) plus a
  framework-free `domain/` layer for media/AI integrations.
- Full upload → analysis vertical slice: ffprobe metadata extraction,
  faster-whisper transcription, PySceneDetect scene detection, and
  LLM-driven summary/title/description/hashtags/highlight generation,
  orchestrated as a Celery chain/chord/group.
- Pluggable AI provider architecture (`domain/ai/registry.py`) with a
  local-first default (Ollama) and a hosted alternative (OpenRouter).
- REST API (DRF, `/api/v1/`) and a server-rendered HTMX-polled frontend
  for upload and the analysis report.
- Docker Compose dev/prod setup (Postgres, Redis, Ollama, web, worker,
  nginx), Makefile, pre-commit hooks, GitHub Actions CI, Dependabot.
- Documentation: architecture, AI pipeline, quick start, installation,
  deployment, Docker, coding standards, development, API, roadmap,
  backlog.
- **Phase 2**: `apps.export_settings.ExportSettings` — the full
  customization schema from the brief (duration, aspect ratio, captions,
  font, color theme, transitions, music, subtitle language, voice-over,
  AI creativity, B-roll type, image-gen/web-search toggles, highlight
  count, quality, export format), a "Customize" panel on the video detail
  page, and a matching `/api/v1/videos/{id}/settings/` endpoint.
  `num_highlights` and AI creativity level (mapped to LLM `temperature`)
  are wired to live behavior and re-run just the analysis step on change;
  the rest are stored for the phase 3 renderer to read later.
- **Phase 3**: `domain/rendering/` + `apps.renders.RenderJob` — the actual
  FFmpeg render. Selects highlights chronologically (greedily fit to
  `output_duration_seconds`), crops/scales to the target aspect ratio,
  burns in styled `.ass` captions with timestamps remapped onto the new
  concatenated timeline, applies transitions, and encodes to the
  requested quality/format. A "Render" panel on the video detail page and
  `/api/v1/videos/{id}/renders/` + `/api/v1/render-jobs/{id}/`.
  `RenderJob.settings_snapshot` freezes the rendering-relevant
  `ExportSettings` fields at creation time so a completed render can't
  silently drift if settings change afterward. B-roll and background
  music remain deferred to phase 4; transitions/karaoke captions/subtitle
  translation ship as disclosed simplifications — see
  [docs/roadmap.md](docs/roadmap.md).
- `apps.common.task_utils.task_failure_guard` — the never-stuck-silently
  Celery failure-handling mechanism (see Fixed, below) generalized out of
  `apps.videos.task_utils.pipeline_task_guard` so `apps.renders` gets the
  identical guarantee without duplicating it.

### Fixed

- Pipeline tasks could get stuck indefinitely showing an in-progress
  status with no error if a transient provider failure exhausted its
  Celery retries — `@shared_task(autoretry_for=...)` re-raises outside the
  task function once retries run out, where no in-function try/except can
  catch it. Replaced with `apps.videos.task_utils.pipeline_task_guard`,
  which handles retries manually and always marks the video `FAILED` with
  a message on any unrecoverable error.
- Ollama/OpenRouter 4xx responses (e.g. a model that was never pulled)
  were being retried as transient failures instead of failing fast.
- The analysis prompt embedded the full transcript with no size cap,
  scaling unbounded with source video length; now downsampled to a fixed
  character budget, evenly across the whole video.
- `docker-compose.yml`'s `.:/app` bind mount shadowed the image's
  `.venv`, breaking every installed package in `web`/`worker` at
  container start; added an anonymous `/app/.venv` volume.
- `docker-compose.prod.yml`'s `ports: []` overrides were silent no-ops
  (Compose merges, not replaces, `ports`/`volumes` across `-f` files) —
  switched to Compose's `!override` merge-control tag.

[Unreleased]: https://github.com/donaldte/reeler/compare/main...HEAD
