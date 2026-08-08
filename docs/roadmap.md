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
  keep rendering fully offline.
- Transitions (fake fade-to-black) and B-roll used to be listed here as
  simplifications/gaps — both are now real, see the pass below.

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

## Real video editing pass — done

The biggest single pass yet, prompted by feedback that a render didn't
look like a real edit: no true transitions, no images, no logo, no
motion, and no way to export more than a short highlight reel.

- **`export_mode`**: a genuinely new render mode, not an extension of the
  highlight-reel one. `"highlight_reel"` (default, unchanged) picks a
  subset of AI-selected moments to fit `output_duration_seconds`.
  `"full_video"` (new) keeps 100% of the source, in order — no clip
  selection/extraction/concatenation at all, just crop/scale + the same
  captions/B-roll/logo/music polish composed in a **single** ffmpeg pass
  (`domain/rendering/ffmpeg_commands.py::build_full_video_render_command`,
  `renderer.py::_render_full_video`). `output_duration_seconds`/
  `num_highlights` are unused in this mode. Their own validators were
  also relaxed (`num_highlights` 10→30, `output_duration_seconds`'
  240s/4-minute cap removed) so a longer curated highlight reel is
  reachable too, independent of full-video mode.
- **True crossfade transitions** (`domain/rendering/ffmpeg_commands.py::
  build_crossfade_concat_command`): real `xfade`/`acrossfade` between
  concatenated highlight clips, replacing the old per-clip fade-to-black.
  Requires ffmpeg ≥ 4.3. `TransitionStyle.ZOOM` maps to xfade's plain
  `"fade"` transition rather than `"zoomin"` for now — `zoomin` shipped
  in a later ffmpeg release than the base xfade filter, a real
  version-compatibility risk not yet confirmed on real hardware; trivial
  one-line upgrade once it is. A single surviving highlight (a real,
  reachable case) always falls back to the plain hard-cut concat
  regardless of `transition_style` — nothing to cross-fade with one clip.
  The AI's per-highlight `"cut"` override only has meaning in the
  `transition_style="none"` hard-cut path now — mixing hard-cut and
  crossfade seams in one `xfade` chain would need per-seam offset-math
  branching, a documented limitation rather than a silently dropped one.
- **Real B-roll** (`ExportSettings.BrollType.STOCK_FOOTAGE`, now actually
  implemented — `AI_GENERATED`/`MIXED` stay inert, see Phase 4 below):
  the same LLM analysis call that produces highlights now also suggests
  up to 5 short B-roll moments (`broll_suggestions` — a fixed,
  non-user-facing cap to protect the CPU-only generation-time budget, see
  `docs/ai_pipeline.md`), each a short visual search query. A new
  `domain.stock_media` capability (mirrors `domain.ai`'s ABC+registry+
  provider pattern exactly, reusing `domain.ai.providers.http_utils`'
  error classification unchanged) searches Pexels and downloads the top
  result as a new `apps.highlights.models.BrollAsset` — a second child of
  `AnalysisResult`, populated best-effort right after analysis completes
  (a Pexels failure — no key, rate limit, no results — skips just that
  suggestion and never turns a successful analysis into a failed video).
  `domain/rendering/broll.py` composites each asset full-frame over its
  window with a Ken Burns pan/zoom (`zoompan`) and a short crossfade
  in/out, remapped from the source video's timeline onto the render's
  output timeline the same way `captions.py` remaps transcript segments.
- **Logo/watermark**: `ExportSettings.logo_image`, composited last in the
  filter chain (after captions/B-roll — brand always wins the stacking
  order) at fixed opacity in a fixed corner, in both render modes.
- Full pass detail, including the exact filter-graph composition and the
  worked crossfade-offset math, lives in code comments/docstrings across
  `domain/rendering/{ffmpeg_commands,broll,renderer}.py` — this entry is
  the summary, not the source of truth.

**Explicitly out of scope for this pass** (deliberate, not forgotten):
Pixabay as a second stock-media provider (same pattern, trivial
follow-up); AI-generated B-roll images (needs a hosted image-gen API —
no GPU on the reference hardware makes local generation impractical, see
Phase 4); word-by-word karaoke captions (needs word-level Whisper
timestamps, unrelated to any of the above).

## Phase 4 — media sourcing

- **Pixabay**: a second `domain.stock_media` provider alongside Pexels
  (same ABC/registry pattern, already built — see the pass above).
- **AI image generation**: `domain.ai.base.ImageGenProvider` already has
  an interface — implement it against a hosted API (a local Stable
  Diffusion/Flux default was the original plan, but is impractical on
  CPU-only reference hardware — this needs its own scoping pass to
  reconsider that default) for `ExportSettings.BrollType.AI_GENERATED`/
  `MIXED`, still inert.
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
