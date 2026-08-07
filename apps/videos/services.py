"""Orchestration glue for apps.videos — the only place that creates an
UploadedVideo from an upload and kicks off the Celery pipeline, and the
shared helpers every pipeline app (transcripts/scenes/highlights) uses to
report progress back onto the same UploadedVideo row.

Called directly from the upload view/serializer (not via a Django signal)
so the control flow stays traceable and easy to unit test.
"""

from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from apps.accounts.models import User
from apps.videos.models import Project, UploadedVideo


def get_or_create_default_project(owner: User) -> Project:
    """Phase 1 has no project-management UI yet — every user gets a single
    implicit default project their uploads land in.
    """
    project, _ = Project.objects.get_or_create(
        owner=owner,
        title="My Videos",
        defaults={"description": "Default project for quick uploads."},
    )
    return project


def create_video_and_launch_pipeline(*, owner: User, uploaded_file: UploadedFile) -> UploadedVideo:
    from apps.videos.tasks import run_analysis_pipeline  # local import avoids a cycle with tasks.py

    project = get_or_create_default_project(owner)
    video = UploadedVideo(
        project=project,
        file=uploaded_file,
        original_filename=uploaded_file.name or "upload",
        file_size_bytes=uploaded_file.size,
    )
    video.init_pipeline_steps()
    video.save()

    run_analysis_pipeline(str(video.id))
    return video


def update_pipeline_step(video_id: str, step: str, step_status: str) -> None:
    """Atomically update a single key in `pipeline_steps`.

    Uses select_for_update because transcription and scene detection run
    concurrently (see apps/videos/tasks.py::run_analysis_pipeline) and both
    write to the same JSON column — without locking, the second writer's
    read-modify-write could silently drop the first writer's update.
    """
    with transaction.atomic():
        video = UploadedVideo.objects.select_for_update().get(id=video_id)
        steps = dict(video.pipeline_steps or {})
        steps[step] = step_status
        video.pipeline_steps = steps
        video.save(update_fields=["pipeline_steps", "updated_at"])


def set_status(
    video_id: str,
    status: str,
    *,
    progress_percent: int | None = None,
    error_message: str | None = None,
) -> None:
    with transaction.atomic():
        video = UploadedVideo.objects.select_for_update().get(id=video_id)
        video.status = status
        update_fields: list[str] = ["status", "updated_at"]
        if progress_percent is not None:
            video.progress_percent = progress_percent
            update_fields.append("progress_percent")
        if error_message is not None:
            video.error_message = error_message
            update_fields.append("error_message")
        video.save(update_fields=update_fields)


def fail_pipeline(video_id: str, step: str, error_message: str) -> None:
    """Convenience wrapper for the common "one step failed permanently, kill
    the whole pipeline" path used by every app's task on PermanentPipelineError.
    """
    update_pipeline_step(video_id, step, "failed")
    set_status(video_id, UploadedVideo.Status.FAILED, error_message=error_message)


def status_payload(video: UploadedVideo) -> dict[str, Any]:
    """Shape returned by both the DRF status endpoint and the HTMX fragment."""
    return {
        "status": video.status,
        "status_display": video.get_status_display(),
        "progress_percent": video.progress_percent,
        "pipeline_steps": video.pipeline_steps,
        "error_message": video.error_message,
        "is_terminal": video.is_terminal,
    }
