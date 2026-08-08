"""Tests for pipeline_task_guard — specifically the bug this fixes: a
TransientProviderError that exhausts its retries must mark the video
FAILED, not leave it silently stuck at whatever status it was mid-pipeline.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.videos.task_utils import pipeline_task_guard
from apps.videos.tests.factories import UploadedVideoFactory
from domain.exceptions import PermanentPipelineError, TransientProviderError

pytestmark = pytest.mark.django_db


def _fake_task(*, retries: int, max_retries: int | None = 3):
    """A minimal stand-in for a bound Celery Task — just enough surface
    (.request.retries, .max_retries, .retry()) for pipeline_task_guard.
    """
    task = SimpleNamespace(request=SimpleNamespace(retries=retries), max_retries=max_retries)
    task.retry = lambda exc, countdown: (_ for _ in ()).throw(_RetryCalled(exc, countdown))
    return task


class _RetryCalled(Exception):
    """Stand-in for the Retry control-flow exception self.retry() raises."""

    def __init__(self, exc, countdown):
        super().__init__("retry called")
        self.exc = exc
        self.countdown = countdown


def test_permanent_error_marks_failed_and_reraises():
    video = UploadedVideoFactory()
    task = _fake_task(retries=0)

    with (
        pytest.raises(PermanentPipelineError),
        pipeline_task_guard(task, str(video.id), "transcript"),
    ):
        raise PermanentPipelineError("corrupt file")

    video.refresh_from_db()
    assert video.status == "failed"
    assert video.pipeline_steps["transcript"] == "failed"
    assert "corrupt file" in video.error_message


def test_transient_error_with_retries_left_calls_self_retry_and_does_not_mark_failed():
    video = UploadedVideoFactory()
    task = _fake_task(retries=0, max_retries=3)

    with pytest.raises(_RetryCalled), pipeline_task_guard(task, str(video.id), "transcript"):
        raise TransientProviderError("ollama connection refused")

    # Not marked failed — a retry was scheduled instead. This is the
    # in-progress case; only exhausting retries should mark FAILED.
    video.refresh_from_db()
    assert video.status != "failed"


def test_transient_error_exhausted_retries_marks_failed_and_reraises_original():
    """This is the exact bug report: Ollama (or any transient provider)
    keeps failing, retries run out, and the video must end up FAILED with
    a clear message instead of stuck forever at its last in-progress status.
    """
    video = UploadedVideoFactory()
    task = _fake_task(retries=3, max_retries=3)  # already at the limit

    with (
        pytest.raises(TransientProviderError, match="ollama timed out"),
        pipeline_task_guard(task, str(video.id), "analysis"),
    ):
        raise TransientProviderError("ollama timed out")

    video.refresh_from_db()
    assert video.status == "failed"
    assert video.pipeline_steps["analysis"] == "failed"
    assert "Gave up after 3 retries" in video.error_message
    assert "ollama timed out" in video.error_message


def test_unexpected_exception_marks_failed_and_reraises():
    """The safety net: a bug, a DB error, a Celery SoftTimeLimitExceeded —
    anything not explicitly modeled as Permanent/TransientProviderError
    must still mark the video FAILED rather than leaving it stuck.
    """
    video = UploadedVideoFactory()
    task = _fake_task(retries=0)

    with (
        pytest.raises(RuntimeError, match="totally unexpected"),
        pipeline_task_guard(task, str(video.id), "scenes"),
    ):
        raise RuntimeError("totally unexpected")

    video.refresh_from_db()
    assert video.status == "failed"
    assert video.pipeline_steps["scenes"] == "failed"
    assert "Unexpected error" in video.error_message
    assert "totally unexpected" in video.error_message


def test_successful_block_does_not_touch_status():
    video = UploadedVideoFactory()
    task = _fake_task(retries=0)

    with pipeline_task_guard(task, str(video.id), "transcript"):
        pass  # no exception — the common case

    video.refresh_from_db()
    assert video.status != "failed"
    assert video.error_message == ""


def test_retry_delay_backs_off_and_caps():
    video = UploadedVideoFactory()
    task = _fake_task(retries=5, max_retries=10)  # not yet exhausted

    with (
        patch.object(task, "retry", wraps=task.retry) as mock_retry,
        pytest.raises(_RetryCalled),
        pipeline_task_guard(task, str(video.id), "transcript"),
    ):
        raise TransientProviderError("boom")

    # 60 * 2**5 = 1920, capped at RETRY_MAX_DELAY_SECONDS (900)
    _, kwargs = mock_retry.call_args
    assert kwargs["countdown"] == 900
