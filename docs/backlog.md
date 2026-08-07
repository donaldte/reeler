# Feature Backlog

Smaller, concrete, mostly-unclaimed items — good starting points for a
first contribution. Larger initiatives live in [docs/roadmap.md](roadmap.md).
Check GitHub Issues for up-to-date claims/status; this file is a seed list,
not the source of truth.

## Good first issues

- [ ] Add a `/videos/` list page with pagination (currently only the last
      20 show on the upload page).
- [ ] Add a "delete video" action (view + API), including cleaning up the
      uploaded file from storage.
- [ ] Add a `--dry-run` flag or admin action to re-run a failed pipeline
      step without re-uploading.
- [ ] Surface `TranscriptSegment.confidence` in the transcript UI (e.g.
      dim low-confidence words).
- [ ] Add a health check for Celery worker liveness (beyond the Django
      `/healthz/` HTTP check).
- [ ] Add `django-extensions`' `shell_plus` for a nicer `make shell`.

## Medium

- [ ] DB-driven provider override: check `apps.ai_providers.AIProviderConfig`
      in `domain/ai/registry.py` before falling back to the env default
      (the model already exists — see docs/ai_pipeline.md).
- [ ] Rate-limit uploads per user (DRF throttling).
- [ ] Add `django-storages` support for S3-compatible media storage as an
      alternative to the local `media_files` volume.
- [ ] Structured JSON logging output option (currently plain-text via
      Python's `logging`) for log-aggregator-friendly deployments.
- [ ] Add a Celery task for periodic cleanup of orphaned/failed uploads
      older than N days.

## Needs design discussion first

- [ ] `ExportSettings` model shape (phase 2 — see roadmap).
- [ ] Rendering pipeline architecture (phase 3 — see roadmap).
- [ ] Stock media provider interface (phase 4 — see roadmap).

Have an idea not listed here? Open an issue using the feature request
template.
