import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from celery import Task, shared_task
from django.core.files import File

from apps.common.task_utils import task_failure_guard
from apps.renders.models import RenderJob
from apps.renders.services import (
    fail_render,
    mark_render_completed,
    mark_rendering,
    update_render_progress,
)
from domain.exceptions import PermanentPipelineError
from domain.rendering.renderer import render_video

logger = logging.getLogger("reeler")


@shared_task(bind=True, acks_late=True, max_retries=1)
def render_video_task(self: Task, render_job_id: str) -> str:
    """Runs the full domain.rendering pipeline for one RenderJob.

    `max_retries=1` is a thin safety net, not the primary flow — ffmpeg
    failures raised by domain.rendering are always PermanentPipelineError
    (deterministic: bad params, unsupported codec, corrupt input), so this
    task's retry path is effectively unreachable in practice, same as
    documented in domain/rendering/renderer.py.
    """
    mark_rendering(render_job_id)

    with task_failure_guard(
        self,
        label=f"Render job {render_job_id}",
        on_failure=lambda msg: fail_render(render_job_id, msg),
    ):
        render_job = RenderJob.objects.select_related(
            "video", "video__transcript", "video__analysis_result"
        ).get(id=render_job_id)
        video = render_job.video

        if not hasattr(video, "analysis_result"):
            raise PermanentPipelineError("Video has no analysis result to render from.")
        highlights = list(video.analysis_result.highlights.all())
        if not highlights:
            raise PermanentPipelineError("No highlights available to render.")
        transcript_segments = (
            list(video.transcript.segments.all()) if hasattr(video, "transcript") else []
        )

        with TemporaryDirectory() as workdir_str:
            workdir = Path(workdir_str)
            output_path = render_video(
                source_path=Path(video.file.path),
                source_width=video.width or 0,
                source_height=video.height or 0,
                has_audio=bool(video.has_audio),
                transcript_segments=transcript_segments,
                highlights=highlights,
                settings_snapshot=render_job.settings_snapshot,
                workdir=workdir,
                progress_callback=lambda pct, stage: update_render_progress(
                    render_job_id, pct, stage
                ),
            )
            export_format = render_job.settings_snapshot["export_format"]
            with open(output_path, "rb") as fh:
                # save=False: this instance was fetched before mark_rendering
                # / update_render_progress ran their own targeted `.update()`
                # calls, so a full `instance.save()` here would clobber
                # status/progress_percent with stale in-memory values.
                # update_fields keeps this write scoped to just the file.
                render_job.output_file.save(
                    f"{render_job_id}.{export_format}", File(fh), save=False
                )
            render_job.save(update_fields=["output_file", "updated_at"])

        mark_render_completed(render_job_id)

    return render_job_id
