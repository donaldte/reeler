from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.videos.constants import ALL_PIPELINE_STEPS, STEP_PENDING


def upload_video_path(instance: "UploadedVideo", filename: str) -> str:
    return f"videos/{instance.project_id}/{instance.id}/{filename}"


class Project(TimeStampedModel):
    """A workspace grouping one or more source video uploads. Phase 1 gives
    every user an implicit default project via the upload view; a dedicated
    project-management UI is future work (see docs/roadmap.md).
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "videos_project"

    def __str__(self) -> str:
        return self.title


class UploadedVideo(TimeStampedModel):
    """A user-uploaded source video and the state of its analysis pipeline.

    `status` / `progress_percent` / `pipeline_steps` are updated by the
    Celery tasks in this app and in apps.transcripts/apps.scenes/
    apps.highlights as the pipeline progresses — see
    apps/videos/tasks.py::run_analysis_pipeline for the orchestration.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        EXTRACTING_METADATA = "extracting_metadata", "Extracting metadata"
        TRANSCRIBING_AND_DETECTING_SCENES = (
            "transcribing_and_detecting_scenes",
            "Transcribing & detecting scenes",
        )
        ANALYZING = "analyzing", "Analyzing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="videos")
    file = models.FileField(upload_to=upload_video_path)
    original_filename = models.CharField(max_length=255)
    file_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)

    # Populated by domain.media.ffprobe via apps/videos/tasks.py::extract_metadata_task
    duration_seconds = models.FloatField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    fps = models.FloatField(null=True, blank=True)
    has_audio = models.BooleanField(null=True, blank=True)
    video_codec = models.CharField(max_length=64, blank=True, default="")
    audio_codec = models.CharField(max_length=64, blank=True, default="")

    status = models.CharField(max_length=40, choices=Status.choices, default=Status.PENDING)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    pipeline_steps = models.JSONField(
        default=dict, blank=True, help_text="Per-step status, e.g. {'transcript': 'running'}."
    )
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "videos_uploaded_video"

    def __str__(self) -> str:
        return self.original_filename

    def init_pipeline_steps(self) -> None:
        """Reset all pipeline step statuses to pending — called once when
        the upload is first saved, and again on a manual re-run.
        """
        self.pipeline_steps = dict.fromkeys(ALL_PIPELINE_STEPS, STEP_PENDING)

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.COMPLETED, self.Status.FAILED}
