from django.db import models

from apps.common.models import TimeStampedModel
from apps.videos.models import UploadedVideo


class Scene(TimeStampedModel):
    """A detected shot boundary, from domain.scene_detection (PySceneDetect).

    When PySceneDetect finds no cuts at all, apps/scenes/tasks.py falls back
    to a single Scene spanning the whole video, so every completed video has
    at least one Scene row.
    """

    video = models.ForeignKey(UploadedVideo, on_delete=models.CASCADE, related_name="scenes")
    index = models.PositiveIntegerField()
    start_time = models.FloatField()
    end_time = models.FloatField()

    class Meta:
        db_table = "scenes_scene"
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["video", "index"], name="unique_scene_index_per_video")
        ]

    def __str__(self) -> str:
        return f"Scene {self.index} [{self.start_time:.1f}-{self.end_time:.1f}]"
