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

## Phase 2 — customization settings UI — done

- `apps.export_settings.models.ExportSettings` — the full schema from the
  brief (output duration, aspect ratio, caption style/font/color theme,
  transition style, music style, subtitle language, voice-over style, AI
  creativity level, B-roll type, image-gen toggle, internet media search
  toggle, number of highlights, video quality, export format). FK (not
  O2O) to `UploadedVideo`, so phase 3 can support multiple render variants
  from one analysis later; phase 2 always works with the latest row via
  `get_or_create_export_settings`.
- A "Customize" panel embedded on the video detail page (plain form POST
  + Django messages, no separate page) and a matching
  `GET`/`PATCH /api/v1/videos/{id}/settings/` API.
- Two fields are actually wired to live behavior today —
  `num_highlights` and `ai_creativity_level` (mapped to LLM sampling
  `temperature`) — both threaded through
  `domain.ai.base.LLMProvider.generate_analysis` into the Ollama/
  OpenRouter providers' request payloads. Changing either on an
  already-`COMPLETED` video re-runs just the analysis step
  (`apps.videos.tasks.rerun_analysis_only`), not the whole pipeline.
- Every other field is schema-complete and saved, but genuinely has no
  effect yet — clearly labeled as such in the UI — until phase 3 exists to
  read it.

## Phase 3 — rendering / export pipeline — done

The FFmpeg-driven cut-together of the final short, from the selected
highlights through to a downloadable video:

- `domain/rendering/` — pure command-building layer (no provider/registry
  abstraction — there's only one way to invoke ffmpeg): `clip_selection.py`
  (chronological, greedily fit to `output_duration_seconds`),
  `dimensions.py` (aspect-ratio/quality → resolution table + center-crop
  math), `captions.py` (`.ass` generation with per-clip timestamp
  remapping), `ffmpeg_commands.py` (pure argv builders), `renderer.py`
  (the one module with subprocess side effects — same
  fixed-argv/no-shell/captured-stderr pattern as `domain/media/ffprobe.py`).
- `apps/renders/` — `RenderJob` (FK to both `UploadedVideo` and
  `ExportSettings`, plus a frozen `settings_snapshot` JSON so a completed
  render always reflects exactly what was requested even if settings
  changed afterward), Celery task, progress reporting, a "Render" panel
  on the video detail page, and `/api/v1/videos/{id}/renders/` +
  `/api/v1/render-jobs/{id}/`.
- The `pipeline_task_guard` failure-handling mechanism (see Phase 1's
  Fixed changelog entry) was generalized into
  `apps.common.task_utils.task_failure_guard` so `apps/renders` gets the
  identical never-stuck-silently guarantee without duplicating it.

**Disclosed simplifications, not silent gaps** (see
`domain/rendering/captions.py`, `ffmpeg_commands.py` docstrings):

- **Transitions**: `fade`/`slide`/`zoom` all currently render as the same
  short fade-in/fade-out on each clip, not true crossfade between clips.
  `xfade`-based crossfades need precise stream-timing alignment between
  two inputs — a real fast-follow once this simpler version is confirmed
  working on real hardware (see [docs/development.md](development.md) for
  why command-construction correctness and execution correctness had to
  be verified separately for this feature). Since the quality pass below,
  each highlight can also carry its own AI-suggested `cut`/`fade`
  preference, which refines (never overrides) this global setting.
- **Karaoke captions**: `caption_style="karaoke"` renders identically to
  `"bold"` — true word-by-word highlighting needs word-level timestamps,
  and `FasterWhisperProvider` currently requests `word_timestamps=False`.
  Flipping that on and threading word-level timing through is the
  concrete next step for this one.
- **Subtitle translation**: `subtitle_language` values other than
  `"auto"`/the transcript's own detected language still render the
  original-language transcript — no translation capability exists yet.
- **Background music** is generated procedurally with ffmpeg's own
  `lavfi` synthetic sources (`domain/rendering/music.py`) — a simple
  layered ambient pad per `music_style`, not a curated real track. No
  downloaded/bundled audio, deliberately, to avoid licensing risk and
  keep rendering fully offline. **B-roll** (real or AI-generated stock
  footage/images) remains fully deferred to Phase 4 (see below) —
  `ExportSettings.broll_type` stays saved-but-inert.

**Render quality & reliability pass** (post-launch, after the first real
render came out far short of its target duration):

- **Highlight-count reliability**: the analysis prompt's schema example
  used to show a single highlight object in its array — a plausible
  reason smaller local models under-delivered on `num_highlights` (an
  observed case: 3 requested, 1 returned, so the render came out to
  ~23s instead of 60s). The example now shows two, the instruction text
  is unhedged ("EXACTLY N" instead of "up to N"), and
  `generate_analysis_with_repair` also retries once on a valid-but-short
  count, not just invalid JSON — without ever discarding a short-but-valid
  result in favor of failing outright. See
  `domain/ai/prompts/highlight_extraction.py` and
  [docs/ai_pipeline.md](ai_pipeline.md).
- **Per-highlight emoji**: the LLM suggests one emoji per highlight as a
  caption accent, shown once on the clip's first caption line — never
  altering the transcript text itself.
- **Caption box polish**: larger fonts, heavier outline, and more bottom
  margin for the platform-UI safe area — best-effort visual tuning, see
  `domain/rendering/captions.py`.

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
