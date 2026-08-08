"""Orchestration glue for apps.renders — the only place a RenderJob gets
created, mirroring apps.videos.services.create_video_and_launch_pipeline
and apps.export_settings.services.
"""

from apps.export_settings.services import get_or_create_export_settings
from apps.renders.models import RenderJob
from apps.videos.models import UploadedVideo

# The subset of ExportSettings fields the renderer actually reads —
# see domain/rendering/renderer.py::render_video's settings_snapshot usage.
SNAPSHOT_FIELDS = [
    "output_duration_seconds",
    "aspect_ratio",
    "caption_style",
    "font",
    "color_theme",
    "transition_style",
    "subtitle_language",
    "video_quality",
    "export_format",
]


def create_render_job(video: UploadedVideo) -> RenderJob:
    """Validates the video is ready to render, snapshots its current
    export settings, creates the RenderJob, and dispatches the Celery task.

    Raises ValueError (not a Django exception — callers translate it into
    whatever's appropriate for their layer: a flash message for the web
    view, a 400 for the API) if the video hasn't finished analysis yet.
    """
    if video.status != UploadedVideo.Status.COMPLETED:
        raise ValueError("Video analysis must complete before rendering.")
    if not hasattr(video, "analysis_result") or not video.analysis_result.highlights.exists():
        raise ValueError("No highlights available to render — analysis produced none.")

    export_settings = get_or_create_export_settings(video)
    snapshot = {field: getattr(export_settings, field) for field in SNAPSHOT_FIELDS}

    render_job = RenderJob.objects.create(
        video=video, export_settings=export_settings, settings_snapshot=snapshot
    )

    from apps.renders.tasks import render_video_task  # avoids a module-load cycle

    render_video_task.delay(str(render_job.id))
    return render_job


def mark_rendering(render_job_id: str, *, progress_percent: int = 5) -> None:
    RenderJob.objects.filter(id=render_job_id).update(
        status=RenderJob.Status.RENDERING, progress_percent=progress_percent
    )


def update_render_progress(render_job_id: str, progress_percent: int, stage: str) -> None:
    RenderJob.objects.filter(id=render_job_id).update(
        progress_percent=progress_percent, stage=stage
    )


def mark_render_completed(render_job_id: str) -> None:
    RenderJob.objects.filter(id=render_job_id).update(
        status=RenderJob.Status.COMPLETED, progress_percent=100, stage="done"
    )


def fail_render(render_job_id: str, message: str) -> None:
    RenderJob.objects.filter(id=render_job_id).update(
        status=RenderJob.Status.FAILED, error_message=message
    )
