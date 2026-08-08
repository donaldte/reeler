# API

Reeler's REST API is versioned under `/api/v1/`, built with Django REST
Framework, and documented via `drf-spectacular`.

- **OpenAPI schema**: `GET /api/schema/`
- **Interactive docs**: `/api/schema/swagger-ui/`

All endpoints require an authenticated session (`SessionAuthentication`) and
scope results to the requesting user's own videos.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/videos/` | Upload a video, launches the analysis pipeline |
| `GET` | `/api/v1/videos/` | List your uploaded videos |
| `GET` | `/api/v1/videos/{id}/` | Video detail + metadata |
| `GET` | `/api/v1/videos/{id}/status/` | Pipeline status (poll while processing) |
| `GET` | `/api/v1/videos/{video_id}/transcript/` | Full transcript + segments |
| `GET` | `/api/v1/videos/{video_id}/scenes/` | Detected scene boundaries |
| `GET` | `/api/v1/videos/{video_id}/analysis/` | Summary, suggested title/description/hashtags, highlights |
| `GET` | `/api/v1/videos/{video_id}/settings/` | Export settings (creates defaults on first touch) |
| `PATCH` | `/api/v1/videos/{video_id}/settings/` | Update export settings; re-runs analysis if `num_highlights`/`ai_creativity_level` changed on a `COMPLETED` video (response includes `rerun_triggered: bool`) |

Response shapes are defined by the serializers in each app's `api/serializers.py`
(`apps/videos/api/serializers.py`, `apps/transcripts/api/serializers.py`,
`apps/scenes/api/serializers.py`, `apps/highlights/api/serializers.py`,
`apps/export_settings/api/serializers.py`) — those, plus the live Swagger
UI, are the source of truth.

## Error shape

All errors go through `apps.common.exceptions.reeler_exception_handler`, so
every error response has the same shape:

```json
{"error": {"code": "not_found", "message": "..."}}
```

## Roadmap

Endpoints for triggering the (not-yet-implemented) final render/export step
and project management are planned — see [docs/roadmap.md](roadmap.md).
