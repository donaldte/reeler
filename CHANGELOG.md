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

[Unreleased]: https://github.com/reeler-video/reeler/compare/main...HEAD
