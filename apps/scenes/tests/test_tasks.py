from unittest.mock import patch

import pytest

from apps.scenes.models import Scene
from apps.scenes.tasks import detect_scenes_task
from apps.videos.constants import PIPELINE_STEP_SCENES, STEP_DONE
from apps.videos.tests.factories import UploadedVideoFactory
from domain.scene_detection.base import SceneDTO

pytestmark = pytest.mark.django_db


def test_detect_scenes_task_persists_scenes():
    video = UploadedVideoFactory(duration_seconds=20.0)
    fake_scenes = [SceneDTO(index=0, start=0.0, end=10.0), SceneDTO(index=1, start=10.0, end=20.0)]

    with patch("apps.scenes.tasks.PySceneDetectProvider.detect", return_value=fake_scenes):
        detect_scenes_task(str(video.id))

    assert Scene.objects.filter(video=video).count() == 2
    video.refresh_from_db()
    assert video.pipeline_steps[PIPELINE_STEP_SCENES] == STEP_DONE


def test_detect_scenes_task_falls_back_to_single_scene_when_no_cuts():
    video = UploadedVideoFactory(duration_seconds=12.0)

    with patch("apps.scenes.tasks.PySceneDetectProvider.detect", return_value=[]):
        detect_scenes_task(str(video.id))

    scenes = list(Scene.objects.filter(video=video))
    assert len(scenes) == 1
    assert scenes[0].start_time == 0.0
    assert scenes[0].end_time == 12.0


def test_detect_scenes_task_is_idempotent_on_rerun():
    video = UploadedVideoFactory(duration_seconds=20.0)
    fake_scenes = [SceneDTO(index=0, start=0.0, end=20.0)]

    with patch("apps.scenes.tasks.PySceneDetectProvider.detect", return_value=fake_scenes):
        detect_scenes_task(str(video.id))
        detect_scenes_task(str(video.id))

    assert Scene.objects.filter(video=video).count() == 1
