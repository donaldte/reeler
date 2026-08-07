from unittest.mock import patch

import pytest

from apps.videos.constants import PIPELINE_STEP_METADATA, STEP_DONE, STEP_FAILED
from apps.videos.models import UploadedVideo
from apps.videos.tasks import extract_metadata_task
from apps.videos.tests.factories import UploadedVideoFactory
from domain.exceptions import UnsupportedMediaError
from domain.media.dto import MediaMetadata

pytestmark = pytest.mark.django_db

FAKE_METADATA = MediaMetadata(
    duration_seconds=42.0,
    width=1280,
    height=720,
    fps=24.0,
    has_audio=True,
    video_codec="h264",
    audio_codec="aac",
    file_size_bytes=999,
)


def test_extract_metadata_task_populates_video_fields():
    video = UploadedVideoFactory()

    with patch("apps.videos.tasks.probe", return_value=FAKE_METADATA):
        extract_metadata_task(str(video.id))

    video.refresh_from_db()
    assert video.duration_seconds == 42.0
    assert video.width == 1280
    assert video.height == 720
    assert video.has_audio is True
    assert video.pipeline_steps[PIPELINE_STEP_METADATA] == STEP_DONE
    assert video.status == UploadedVideo.Status.TRANSCRIBING_AND_DETECTING_SCENES
    assert video.progress_percent == 15


def test_extract_metadata_task_marks_failed_on_permanent_error():
    video = UploadedVideoFactory()

    with (
        patch("apps.videos.tasks.probe", side_effect=UnsupportedMediaError("corrupt file")),
        pytest.raises(UnsupportedMediaError),
    ):
        extract_metadata_task(str(video.id))

    video.refresh_from_db()
    assert video.status == UploadedVideo.Status.FAILED
    assert video.pipeline_steps[PIPELINE_STEP_METADATA] == STEP_FAILED
    assert "corrupt file" in video.error_message
