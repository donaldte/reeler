from django.db import models

from apps.common.models import TimeStampedModel
from apps.export_settings.models import ExportSettings
from apps.videos.models import UploadedVideo


def render_output_path(instance: "RenderJob", filename: str) -> str:
    return f"renders/{instance.video_id}/{instance.id}/{filename}"


class RenderJob(TimeStampedModel):
    """One FFmpeg render attempt for a video — cuts the selected highlights
    together, cropped to the target aspect ratio, with captions burned in.
    See domain/rendering/renderer.py and apps/renders/tasks.py.

    Multiple RenderJobs per video are expected (the user can re-render
    after changing settings) — that's exactly why `settings_snapshot`
    exists: `export_settings` is a live, mutable FK for traceability, but
    the task only ever reads the frozen JSON snapshot taken at creation
    time, so a completed render always reflects exactly what was
    requested, even if the video's ExportSettings changed afterward.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RENDERING = "rendering", "Rendering"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    video = models.ForeignKey(UploadedVideo, on_delete=models.CASCADE, related_name="render_jobs")
    export_settings = models.ForeignKey(
        ExportSettings, on_delete=models.SET_NULL, null=True, related_name="render_jobs"
    )
    settings_snapshot = models.JSONField(
        help_text="Rendering-relevant ExportSettings fields captured at creation time."
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    stage = models.CharField(
        max_length=32, blank=True, default="", help_text="Coarse current step, e.g. 'encoding'."
    )
    output_file = models.FileField(upload_to=render_output_path, null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "renders_render_job"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"RenderJob<{self.video_id}, {self.status}>"

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.COMPLETED, self.Status.FAILED}
