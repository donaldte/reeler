from unittest.mock import patch

import pytest

from apps.export_settings.tests.factories import ExportSettingsFactory
from apps.highlights.models import AnalysisResult
from apps.renders.models import RenderJob
from apps.renders.services import (
    create_render_job,
    fail_render,
    mark_render_completed,
    mark_rendering,
    update_render_progress,
)
from apps.renders.tests.factories import RenderJobFactory
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory

pytestmark = pytest.mark.django_db


def _completed_video_with_highlights():
    video = UploadedVideoFactory(status=UploadedVideo.Status.COMPLETED)
    result = AnalysisResult.objects.create(
        video=video, summary="s", suggested_title="t", suggested_description="d",
        suggested_hashtags=[], llm_provider="ollama", llm_model="qwen2.5:3b", raw_response={},
    )  # fmt: skip
    result.highlights.create(rank=1, start_time=0.0, end_time=10.0, rationale="r")
    return video


def test_create_render_job_rejects_non_completed_video():
    video = UploadedVideoFactory(status=UploadedVideo.Status.ANALYZING)
    with pytest.raises(ValueError, match="must complete"):
        create_render_job(video)


def test_create_render_job_rejects_video_with_no_analysis_result():
    video = UploadedVideoFactory(status=UploadedVideo.Status.COMPLETED)
    with pytest.raises(ValueError, match="No highlights"):
        create_render_job(video)


def test_create_render_job_rejects_analysis_with_no_highlights():
    video = UploadedVideoFactory(status=UploadedVideo.Status.COMPLETED)
    AnalysisResult.objects.create(
        video=video, summary="s", suggested_title="t", suggested_description="d",
        suggested_hashtags=[], llm_provider="ollama", llm_model="qwen2.5:3b", raw_response={},
    )  # fmt: skip
    with pytest.raises(ValueError, match="No highlights"):
        create_render_job(video)


def test_create_render_job_snapshots_current_export_settings():
    video = _completed_video_with_highlights()
    ExportSettingsFactory(video=video, aspect_ratio="1:1", num_highlights=7)

    with patch("apps.renders.tasks.render_video_task.delay") as mock_delay:
        render_job = create_render_job(video)

    assert render_job.settings_snapshot["aspect_ratio"] == "1:1"
    assert "num_highlights" not in render_job.settings_snapshot  # not a rendering-relevant field
    assert render_job.export_settings is not None
    mock_delay.assert_called_once_with(str(render_job.id))


def test_create_render_job_uses_default_settings_when_none_saved():
    video = _completed_video_with_highlights()
    with patch("apps.renders.tasks.render_video_task.delay"):
        render_job = create_render_job(video)
    assert render_job.settings_snapshot["aspect_ratio"] == "9:16"  # ExportSettings default


def test_mark_rendering_sets_status_and_progress():
    render_job = RenderJobFactory(status=RenderJob.Status.PENDING)
    mark_rendering(str(render_job.id))
    render_job.refresh_from_db()
    assert render_job.status == RenderJob.Status.RENDERING
    assert render_job.progress_percent == 5


def test_update_render_progress_sets_percent_and_stage():
    render_job = RenderJobFactory()
    update_render_progress(str(render_job.id), 42, "encoding")
    render_job.refresh_from_db()
    assert render_job.progress_percent == 42
    assert render_job.stage == "encoding"


def test_mark_render_completed():
    render_job = RenderJobFactory()
    mark_render_completed(str(render_job.id))
    render_job.refresh_from_db()
    assert render_job.status == RenderJob.Status.COMPLETED
    assert render_job.progress_percent == 100
    assert render_job.stage == "done"


def test_fail_render():
    render_job = RenderJobFactory()
    fail_render(str(render_job.id), "ffmpeg exploded")
    render_job.refresh_from_db()
    assert render_job.status == RenderJob.Status.FAILED
    assert render_job.error_message == "ffmpeg exploded"
