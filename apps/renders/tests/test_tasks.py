from pathlib import Path
from unittest.mock import patch

import pytest

from apps.highlights.models import AnalysisResult
from apps.renders.models import RenderJob
from apps.renders.tasks import render_video_task
from apps.renders.tests.factories import RenderJobFactory
from apps.transcripts.models import Transcript, TranscriptSegment
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory
from domain.exceptions import PermanentPipelineError

pytestmark = pytest.mark.django_db


def _video_with_transcript_and_analysis():
    video = UploadedVideoFactory(
        status=UploadedVideo.Status.COMPLETED, width=1920, height=1080, has_audio=True
    )
    transcript = Transcript.objects.create(
        video=video, language="en", language_confidence=0.9, full_text="hi",
        provider="faster_whisper", model_name="small",
    )  # fmt: skip
    TranscriptSegment.objects.create(
        transcript=transcript, index=0, start_time=0.0, end_time=2.0, text="hi"
    )
    result = AnalysisResult.objects.create(
        video=video, summary="s", suggested_title="t", suggested_description="d",
        suggested_hashtags=[], llm_provider="ollama", llm_model="qwen2.5:3b", raw_response={},
    )  # fmt: skip
    result.highlights.create(rank=1, start_time=0.0, end_time=2.0, rationale="r")
    return video


def test_render_video_task_marks_completed_and_saves_output_file(tmp_path):
    video = _video_with_transcript_and_analysis()
    render_job = RenderJobFactory(video=video)

    fake_output = tmp_path / "output.mp4"
    fake_output.write_bytes(b"fake video bytes")

    with patch("apps.renders.tasks.render_video", return_value=fake_output) as mock_render:
        render_video_task(str(render_job.id))

    render_job.refresh_from_db()
    assert render_job.status == RenderJob.Status.COMPLETED
    assert render_job.progress_percent == 100
    assert render_job.stage == "done"
    assert render_job.output_file
    assert render_job.output_file.read() == b"fake video bytes"
    mock_render.assert_called_once()
    call_kwargs = mock_render.call_args.kwargs
    assert call_kwargs["source_width"] == 1920
    assert call_kwargs["source_height"] == 1080
    assert call_kwargs["has_audio"] is True
    assert call_kwargs["source_path"] == Path(video.file.path)


def test_render_video_task_marks_rendering_before_starting(tmp_path):
    video = _video_with_transcript_and_analysis()
    render_job = RenderJobFactory(video=video, status=RenderJob.Status.PENDING)
    fake_output = tmp_path / "output.mp4"
    fake_output.write_bytes(b"x")

    seen_statuses = []

    def fake_render(**kwargs):
        seen_statuses.append(RenderJob.objects.get(id=render_job.id).status)
        return fake_output

    with patch("apps.renders.tasks.render_video", side_effect=fake_render):
        render_video_task(str(render_job.id))

    assert seen_statuses == [RenderJob.Status.RENDERING]


def test_render_video_task_fails_when_no_highlights():
    video = UploadedVideoFactory(status=UploadedVideo.Status.COMPLETED)
    AnalysisResult.objects.create(
        video=video, summary="s", suggested_title="t", suggested_description="d",
        suggested_hashtags=[], llm_provider="ollama", llm_model="qwen2.5:3b", raw_response={},
    )  # fmt: skip
    render_job = RenderJobFactory(video=video)

    with pytest.raises(PermanentPipelineError, match="No highlights"):
        render_video_task(str(render_job.id))

    render_job.refresh_from_db()
    assert render_job.status == RenderJob.Status.FAILED
    assert "No highlights" in render_job.error_message


def test_render_video_task_fails_when_no_analysis_result():
    video = UploadedVideoFactory(status=UploadedVideo.Status.COMPLETED)
    render_job = RenderJobFactory(video=video)

    with pytest.raises(PermanentPipelineError, match="no analysis result"):
        render_video_task(str(render_job.id))

    render_job.refresh_from_db()
    assert render_job.status == RenderJob.Status.FAILED


def test_render_video_task_propagates_ffmpeg_failure_as_render_failure():
    video = _video_with_transcript_and_analysis()
    render_job = RenderJobFactory(video=video)

    with (
        patch(
            "apps.renders.tasks.render_video", side_effect=PermanentPipelineError("ffmpeg exploded")
        ),
        pytest.raises(PermanentPipelineError),
    ):
        render_video_task(str(render_job.id))

    render_job.refresh_from_db()
    assert render_job.status == RenderJob.Status.FAILED
    assert "ffmpeg exploded" in render_job.error_message


def test_render_video_task_handles_video_with_no_transcript_gracefully(tmp_path):
    """Defensive path — shouldn't happen in practice since analysis_result
    implies transcript exists earlier in the pipeline, but must not crash.
    """
    video = UploadedVideoFactory(
        status=UploadedVideo.Status.COMPLETED, width=1920, height=1080, has_audio=True
    )
    result = AnalysisResult.objects.create(
        video=video, summary="s", suggested_title="t", suggested_description="d",
        suggested_hashtags=[], llm_provider="ollama", llm_model="qwen2.5:3b", raw_response={},
    )  # fmt: skip
    result.highlights.create(rank=1, start_time=0.0, end_time=2.0, rationale="r")
    render_job = RenderJobFactory(video=video)

    fake_output = tmp_path / "output.mp4"
    fake_output.write_bytes(b"x")

    with patch("apps.renders.tasks.render_video", return_value=fake_output) as mock_render:
        render_video_task(str(render_job.id))

    assert mock_render.call_args.kwargs["transcript_segments"] == []
