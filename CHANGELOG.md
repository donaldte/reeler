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
  silently drift if settings change afterward. Real transitions, B-roll,
  and background music all shipped in later passes below;
  karaoke captions/subtitle translation remain disclosed simplifications
  — see [docs/roadmap.md](docs/roadmap.md).
- `apps.common.task_utils.task_failure_guard` — the never-stuck-silently
  Celery failure-handling mechanism (see Fixed, below) generalized out of
  `apps.videos.task_utils.pipeline_task_guard` so `apps.renders` gets the
  identical guarantee without duplicating it.
- **Render quality & reliability pass**:
  - Procedurally generated background music (`domain/rendering/music.py`)
    — ffmpeg `lavfi` synthetic sources layered per `music_style`, mixed
    under dialogue via `-filter_complex`/`amix` in
    `build_final_encode_command`. No downloaded/bundled audio, kept
    fully offline and licensing-free by design; a simple ambient pad,
    not a curated real track — see [docs/roadmap.md](docs/roadmap.md).
  - Per-highlight AI-suggested `transition` (`cut`/`fade`), refining
    (not overriding) `ExportSettings.transition_style` per clip.
  - Per-highlight AI-suggested `emoji`, shown once as an accent on each
    clip's first caption line — the transcript text itself is never
    altered.
  - Caption box visual polish: larger fonts, heavier outline, more
    bottom margin for the platform-UI safe area.
- **Real video editing pass** (the largest pass yet — see
  [docs/roadmap.md](docs/roadmap.md) for full detail):
  - `ExportSettings.export_mode`: `"highlight_reel"` (default, unchanged
    behavior) or the new `"full_video"` — keeps the entire source video,
    in order, with the same captions/B-roll/logo/music polish composed
    in a single ffmpeg pass (`domain/rendering/renderer.py::_render_full_video`,
    `ffmpeg_commands.py::build_full_video_render_command`). No clip
    selection/extraction/concatenation in this mode.
  - True crossfade transitions (`ffmpeg_commands.py::
    build_crossfade_concat_command`, real `xfade`/`acrossfade`) replace
    the old per-clip fade-to-black for highlight-reel renders. Falls back
    to a plain hard-cut concat for a single surviving clip or
    `transition_style="none"`.
  - Real B-roll: a new `domain.stock_media` capability (Pexels, mirroring
    `domain.ai`'s provider/registry pattern) resolves up to 5
    LLM-suggested `broll_suggestions` per analysis into
    `apps.highlights.models.BrollAsset` rows, composited with a Ken Burns
    pan/zoom (`domain/rendering/broll.py`) in both render modes.
    `ExportSettings.BrollType.STOCK_FOOTAGE` is now live (`AI_GENERATED`/
    `MIXED` remain inert).
  - `ExportSettings.logo_image`: an optional watermark composited last in
    the filter chain (after captions/B-roll) at fixed opacity/corner, in
    both render modes.
  - `num_highlights` max raised 10 → 30; `output_duration_seconds`'
    240s/4-minute cap removed — a longer highlight reel is reachable
    independent of `export_mode="full_video"`.
  - The video detail page and `/api/v1/videos/{id}/analysis/` now list
    every chosen B-roll asset (thumbnail, search query, timestamp
    window) — this data existed in the database from the start of this
    pass but was never surfaced to the user.

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
- A render came out to only ~23s instead of the requested 60s: the
  analysis step's LLM call returned fewer highlights than
  `num_highlights` requested (observed: 1 instead of 3), and nothing
  enforced or corrected that. The prompt's schema example showed only one
  highlight object (likely encouraging models to under-deliver on count),
  and `generate_analysis_with_repair` only retried on invalid JSON, never
  on a valid-but-short highlight count. Fixed in
  `domain/ai/prompts/highlight_extraction.py` — see Added, above, and
  [docs/ai_pipeline.md](docs/ai_pipeline.md).
- `apps/renders/services.py::SNAPSHOT_FIELDS` was missing `"music_style"`
  — added in phase 2 to `ExportSettings` but never wired into
  `RenderJob.settings_snapshot`, so the background-music feature could
  never have activated regardless of what a user picked.
- `export_mode="full_video"` still asked the LLM for `num_highlights`
  highlight moments *to extract*, even though nothing is extracted in
  that mode — wasted CPU-bound generation time and set up the
  count-repair logic to spuriously retry forever trying to force
  highlights the renderer would just discard. Now asks for zero
  highlights in that mode; B-roll suggestions are unaffected. This also
  surfaced (and fixes) a second bug: `apps/renders/services.py::
  create_render_job` and `apps/renders/tasks.py::render_video_task` both
  unconditionally required at least one `Highlight` to exist, which
  would have made every `full_video`-mode video permanently unrenderable.
- The watermark composited at the uploaded logo image's native
  resolution — for any normal photo/logo, that meant it covered most or
  all of the frame instead of sitting as a small corner mark, and there
  was no way to pick which corner. `build_watermark_filter_complex` now
  scales it to ~18% of the output frame's width first; new
  `ExportSettings.logo_position` (default bottom-right) picks the corner.

[Unreleased]: https://github.com/donaldte/reeler/compare/main...HEAD
