import pytest

from apps.videos.constants import ALL_PIPELINE_STEPS, STEP_PENDING
from apps.videos.tests.factories import UploadedVideoFactory

pytestmark = pytest.mark.django_db


def test_init_pipeline_steps_sets_all_steps_pending():
    video = UploadedVideoFactory()
    assert video.pipeline_steps == dict.fromkeys(ALL_PIPELINE_STEPS, STEP_PENDING)


def test_is_terminal_false_for_pending():
    video = UploadedVideoFactory()
    assert video.is_terminal is False


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_is_terminal_true_for_completed_and_failed(status):
    video = UploadedVideoFactory(status=status)
    assert video.is_terminal is True


def test_str_returns_filename():
    video = UploadedVideoFactory(original_filename="my_clip.mp4")
    assert str(video) == "my_clip.mp4"
