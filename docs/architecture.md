# Architecture

## Layering

Reeler splits into two layers with a hard dependency rule: **`domain/`
never imports Django**, and **`apps/*` never contains AI/media logic
directly** — it only calls into `domain/` and maps the result onto ORM
rows.

```
apps/<name>/
  models.py     Django ORM models (the persistence shape)
  admin.py      Django admin registration
  views.py      Django template views (HTML frontend)
  urls.py       Template view routes
  forms.py      Django forms (upload validation, etc.)
  services.py   Orchestration glue — the only place views/API call into
  tasks.py      Celery tasks — thin adapters: call domain/, write to models
  api/
    serializers.py
    views.py    DRF viewsets
    urls.py
  templates/<name>/
  tests/

domain/
  exceptions.py         Shared exception hierarchy (Transient/Permanent)
  media/                ffprobe wrapper
  transcription/        SpeechToTextProvider ABC + implementations
  scene_detection/       SceneDetector ABC + implementation
  ai/                    LLMProvider ABC + implementations, prompts, registry
  tests/                 Unit tests, all I/O mocked
```

Why: `domain/` is framework-free Python — every AI/media integration is
unit-testable with plain mocks (no Django test DB needed), reusable outside
Django (a future CLI, a batch job), and swappable without touching any
app's models or views. `apps/` stays thin: if you're writing business logic
in a `views.py` or `models.py` method, it probably belongs in `services.py`
or `domain/` instead.

## Apps

| App | Owns | Depends on |
|---|---|---|
| `accounts` | Custom `User` model | — |
| `common` | `TimeStampedModel`, DRF exception shape, pagination, template filters, `task_utils.task_failure_guard` (shared Celery failure-handling) | — |
| `videos` | `Project`, `UploadedVideo`; upload flow; pipeline orchestration entrypoint | `accounts`, `common` |
| `transcripts` | `Transcript`, `TranscriptSegment` | `videos`, `domain.transcription` |
| `scenes` | `Scene` | `videos`, `domain.scene_detection` |
| `highlights` | `AnalysisResult`, `Highlight` | `videos`, `transcripts`, `scenes`, `domain.ai`, `export_settings` |
| `export_settings` | `ExportSettings` — analysis/export customization | `videos` |
| `renders` | `RenderJob` — FFmpeg render attempts | `videos`, `export_settings`, `highlights`, `transcripts`, `domain.rendering` |
| `ai_providers` | `AIProviderConfig` catalog (admin visibility only, phase 1) | — |

`apps.videos` is the only app that knows about the *analysis pipeline as a
whole* — its `tasks.py::run_analysis_pipeline` builds the Celery
chain/chord/group that calls into the transcripts/scenes/highlights apps'
tasks, and `tasks.py::rerun_analysis_only` re-triggers just the analysis
step when `export_settings` fields that affect it change. `apps.renders`
is a separate, parallel entrypoint (`services.py::create_render_job` →
`tasks.py::render_video_task`) — rendering doesn't extend the analysis
chain, it's a distinct action the user takes once analysis is done. No app
imports another app's `tasks.py` at module scope; every cross-app task
call (`videos` → transcripts/scenes/highlights, `export_settings` →
`videos.tasks.rerun_analysis_only`, `renders` → itself) is a lazy
in-function import to avoid circular imports at Django app-loading time.

`apps.videos.views.video_detail` is the one place a view reaches into
another app at the Python level rather than through a template
`{% include %}` — it builds an `ExportSettingsForm` because a bound form
can't be constructed purely from a reverse-relation lookup in a template.
`apps.renders`' UI needed no such exception: `video.render_jobs.all` is a
plain reverse relation, rendered directly in
`renders/_render_section.html` the same way the read-only transcript/
scenes/highlights partials work — reinforcing that the `ExportSettingsForm`
case really is a narrow, form-specific exception, not a pattern to spread.

## Data model

```
User ─< Project ─< UploadedVideo ─┬─1 Transcript ─< TranscriptSegment
                                   ├─< Scene
                                   ├─1 AnalysisResult ─< Highlight
                                   ├─< ExportSettings
                                   └─< RenderJob ─→ ExportSettings (FK, traceability only)

AIProviderConfig  (standalone catalog, no FK — see docs/ai_pipeline.md)
```

`RenderJob.export_settings` is a live FK kept for admin/traceability, but
the render task never reads it directly — it reads
`RenderJob.settings_snapshot`, a JSON copy of the rendering-relevant
`ExportSettings` fields taken at creation time, so a completed render
stays accurate even if the video's settings are edited afterward.

Every model inherits `apps.common.models.TimeStampedModel` (UUID primary
key, `created_at`, `updated_at`). `UploadedVideo` is the pipeline's state
machine — see below.

## Pipeline state machine

```
PENDING
  → EXTRACTING_METADATA           (extract_metadata_task)
  → TRANSCRIBING_AND_DETECTING_SCENES   (transcribe_video_task + detect_scenes_task, parallel)
  → ANALYZING                     (generate_analysis_task)
  → COMPLETED | FAILED
```

`UploadedVideo.pipeline_steps` is a JSON map (`{"metadata": "done",
"transcript": "running", "scenes": "done", "analysis": "pending"}`) updated
independently by each task — a single linear percentage can't represent two
steps running concurrently, so the UI renders per-step state instead (see
`apps/videos/templates/videos/_status_fragment.html`).

## Task graph

```python
chain(
    extract_metadata_task.si(video_id),
    chord(
        group(transcribe_video_task.si(video_id), detect_scenes_task.si(video_id)),
        generate_analysis_task.si(video_id),
    ),
).apply_async()
```

`apps.videos.tasks.rerun_analysis_only(video_id)` dispatches just
`generate_analysis_task.si(video_id)` standalone — no chain/chord needed,
since that task already owns its full status transition
(`ANALYZING` → `COMPLETED`) and idempotent write. Used when
`export_settings` fields that affect analysis change on an already-
`COMPLETED` video; see `apps/export_settings/services.py::maybe_rerun_analysis`.

Every task signature is **immutable** (`.si()`) and takes only `video_id` —
tasks always read/write their input/output via PostgreSQL, never through
Celery's Redis result backend. This keeps the payloads small, makes retries
trivially safe (re-read from the DB, don't rely on stale task arguments),
and means `generate_analysis_task` (the chord callback) reconstructs the
`TranscriptionResult`/`SceneDTO` domain objects from the DB rows written by
the two parallel tasks rather than receiving them as Celery return values.

Each task is idempotent on retry: write-tasks wrap in
`transaction.atomic()` and delete any existing child rows for the video
before re-inserting. Every task body runs inside
`apps.videos.task_utils.pipeline_task_guard`, which maps failures onto the
video's status:

- `PermanentPipelineError` → `fail_pipeline()` marks the video `FAILED`
  with an `error_message` immediately, no retry.
- `TransientProviderError` → manually retried via `self.retry()`
  (exponential backoff, capped) *while retries remain*; once exhausted,
  also `fail_pipeline()`s rather than raising silently into the void.
- Anything else (a bug, a `SoftTimeLimitExceeded`, ...) → same
  `fail_pipeline()` safety net, so a video can never end up silently stuck
  mid-pipeline forever with no error shown.

This is deliberately *not* `@shared_task(autoretry_for=...)` — that
decorator wraps the whole task call from the outside, so by the time
retries are exhausted, the re-raise happens in code the task function has
already exited; nothing inside the function, however broad the
try/except, can catch it. See `apps/videos/task_utils.py` for the full
rationale.

**Note on `CELERY_TASK_ALWAYS_EAGER`:** with a real broker (the default),
`apply_async()` returns immediately and a task's exception is only ever
seen by the worker — the upload view/API never blocks or fails because of a
downstream pipeline error. In eager mode (used by the test suite, and
available for a worker-less local setup), the whole chain runs
synchronously inside the caller, so a permanent failure re-raises out of
`create_video_and_launch_pipeline()` itself. See
`apps/videos/tests/test_pipeline_integration.py` for both code paths.

## AI provider plugin architecture

See [docs/ai_pipeline.md](ai_pipeline.md) for the full design — providers,
prompts, and how to add a new backend.

## Frontend

Server-rendered Django templates + Tailwind CSS (utility classes only, no
component framework) + HTMX for the one piece of real interactivity
(polling pipeline status) + Alpine.js vendored for future lightweight
client-side state. No SPA, no build step beyond the Tailwind CLI.

## API

DRF, versioned under `/api/v1/`, schema at `/api/schema/`, Swagger UI at
`/api/schema/swagger-ui/`. Every viewset scopes querysets to
`request.user`'s own videos — see [docs/api.md](api.md).
