import logging
from pathlib import Path
from uuid import UUID

from celery import Task, shared_task
from django.conf import settings
from django.db import transaction

from apps.scenes.models import Scene
from apps.videos.constants import PIPELINE_STEP_SCENES, STEP_DONE, STEP_RUNNING
from apps.videos.models import UploadedVideo
from apps.videos.services import update_pipeline_step
from apps.videos.task_utils import pipeline_task_guard
from domain.exceptions import PermanentPipelineError
from domain.scene_detection.base import SceneDTO
from domain.scene_detection.providers.pyscenedetect_provider import PySceneDetectProvider

logger = logging.getLogger("reeler")


@shared_task(bind=True, acks_late=True, max_retries=3)
def detect_scenes_task(self: Task, video_id: str) -> str:
    """Runs in parallel with transcribe_video_task (see
    apps/videos/tasks.py::run_analysis_pipeline).

    PySceneDetect is currently the only scene-detection backend, so this
    task instantiates it directly rather than going through a registry
    (unlike the STT/LLM capabilities, which have multiple pluggable
    implementations — see domain/ai/registry.py).
    """
    update_pipeline_step(video_id, PIPELINE_STEP_SCENES, STEP_RUNNING)

    with pipeline_task_guard(self, video_id, PIPELINE_STEP_SCENES):
        video = UploadedVideo.objects.get(id=video_id)
        detector = PySceneDetectProvider(
            threshold=settings.SCENE_DETECTION_THRESHOLD,
            min_scene_len_seconds=settings.SCENE_DETECTION_MIN_SCENE_LEN_SECONDS,
        )

        try:
            scenes = detector.detect(Path(video.file.path))
        except PermanentPipelineError:
            raise
        except Exception as exc:
            logger.exception("Scene detection failed unexpectedly for %s", video_id)
            raise PermanentPipelineError(str(exc)) from exc

        if not scenes:
            # No cuts detected (e.g. a single continuous shot) — treat the whole
            # video as one scene so downstream highlight extraction always has
            # at least one scene boundary to reason about.
            scenes = [SceneDTO(index=0, start=0.0, end=video.duration_seconds or 0.0)]

        with transaction.atomic():
            Scene.objects.filter(video_id=UUID(video_id)).delete()
            Scene.objects.bulk_create(
                [
                    Scene(video_id=video_id, index=s.index, start_time=s.start, end_time=s.end)
                    for s in scenes
                ]
            )

        update_pipeline_step(video_id, PIPELINE_STEP_SCENES, STEP_DONE)

    return video_id
