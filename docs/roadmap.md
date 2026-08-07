# Roadmap

Reeler's long-term goal is a full AI video editor: upload a long video, get
a polished, captioned, scored short video out the other end, with heavy
customization along the way. Phase 1 (this scaffold) delivers the
**analysis** half of that; everything below is what's left to reach the
full vision described in the project brief.

## Phase 1 — done

- Upload → metadata (ffprobe) → transcript (faster-whisper) → scenes
  (PySceneDetect) → LLM analysis (summary/title/description/hashtags/
  highlights), fully working end to end.
- Pluggable AI provider architecture (local-first, Ollama default,
  OpenRouter as a hosted alternative) for STT and LLM capabilities.
- Production-shaped repo: Docker/Compose, CI, tests, docs, dev tooling.

## Phase 2 — customization settings UI

The brief calls for a review-and-customize step before rendering: output
duration, aspect ratio (16:9/9:16/1:1), caption style/font/color theme,
transition style, music style, subtitle language, voice-over, AI
creativity level, B-roll type, image-gen on/off, internet media search
on/off, number of highlights, quality, export format. This needs:

- An `ExportSettings` model (per-video, one-to-many so a user can render
  multiple variants from one analysis).
- A settings form/UI on the video detail page.
- Extending the highlight-extraction prompt to accept "creativity level"
  and "number of highlights" as parameters (`domain/ai/prompts/` already
  takes `num_highlights` — creativity level would map to LLM temperature/
  prompt framing).

## Phase 3 — rendering / export pipeline

The actual FFmpeg-driven cut-together of the final short: applying
captions (burned-in, styled per `ExportSettings`), transitions, zoom/pan
effects, overlays, B-roll insertion, and background music, driven by the
selected highlights. This is the largest remaining chunk of work:

- `domain/rendering/` — an FFmpeg command-building layer, likely via a
  filter-graph builder rather than shelling out ad hoc.
  Follows the same wrapper-not-binding pattern as `domain/media/ffprobe.py`.
- `apps/renders/` — `RenderJob` model, Celery task, progress reporting
  (same `pipeline_steps` pattern as the analysis pipeline).
  ​- Caption burn-in: generate an `.ass`/`.srt` from `TranscriptSegment`s,
  styled per `ExportSettings`, burned in via ffmpeg's `subtitles` filter.
- Background music: needs a royalty-free music library or generation
  step (see below) plus loudness normalization against dialogue.

## Phase 4 — media sourcing

- **Royalty-free stock search**: pluggable `StockMediaProvider` interface
  (mirrors the AI provider pattern) — Pexels/Pixabay/Openverse as initial
  backends, selected the same way `AI_LLM_PROVIDER` is.
- **AI image generation**: `domain.ai.base.ImageGenProvider` already has
  an interface — implement it against local Stable Diffusion/Flux
  (`diffusers`) as the local-first default, with a hosted fallback.
- **AI video generation**: further out; interface not yet designed.

## Phase 5 — quality-of-life

- Speaker diarization — `TranscriptSegment.speaker_label` already exists
  in the schema (always `NULL` today); implement via `pyannote.audio` or
  similar and populate it.
- Thumbnail generation (extract/rank candidate frames, or generate one).
- Script generation (a distinct capability from summarization — a
  narration script for voice-over).
- Emotion/object/face detection as inputs to highlight ranking.
- Entry-point-based provider auto-discovery (`importlib.metadata.entry_points`)
  so third-party packages can register providers without editing
  `domain/ai/registry.py` directly.
- Multi-tenancy / teams, usage quotas, billing (if ever needed for a
  hosted offering — the AGPL license is specifically chosen to keep this
  project's own hosted version, if one exists, also open).

## Infrastructure

- Kubernetes manifests / Helm chart for cloud deployment.
- Horizontal Ollama serving (multiple GPU nodes) for larger deployments.
- Object storage backend for `media_files` (S3-compatible) instead of a
  local volume, for multi-node deployments.

See [docs/backlog.md](backlog.md) for smaller, unclaimed issues suitable
for a first contribution.
