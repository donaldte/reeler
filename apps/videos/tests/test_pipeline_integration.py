"""End-to-end test of the full analysis pipeline: upload -> metadata ->
transcript + scenes (parallel) -> analysis, run synchronously via
CELERY_TASK_ALWAYS_EAGER (set in config/settings/test.py).

Every external boundary (ffprobe, the STT provider, the LLM provider) is
mocked — this test verifies the Celery chain/chord/group wiring and the
ORM writes across all four apps, not the AI models themselves (those are
covered by domain/tests/ and each app's own tests/test_tasks.py).
"""

from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.videos.models import UploadedVideo
from apps.videos.services import create_video_and_launch_pipeline
from apps.videos.tests.factories import UserFactory
from domain.ai.base import AnalysisDTO, HighlightDTO
from domain.media.dto import MediaMetadata
from domain.scene_detection.base import SceneDTO
from domain.transcription.base import TranscriptionResult, TranscriptSegmentDTO

pytestmark = pytest.mark.django_db

FAKE_METADATA = MediaMetadata(
    duration_seconds=30.0,
    width=1920,
    height=1080,
    fps=30.0,
    has_audio=True,
    video_codec="h264",
    audio_codec="aac",
    file_size_bytes=1234,
)

FAKE_TRANSCRIPT = TranscriptionResult(
    language="en",
    language_confidence=0.99,
    full_text="Hello world. This is a test video about testing.",
    segments=[
        TranscriptSegmentDTO(index=0, start=0.0, end=2.0, text="Hello world."),
        TranscriptSegmentDTO(
            index=1, start=2.0, end=6.0, text="This is a test video about testing."
        ),
    ],
    provider="faster_whisper",
    model="tiny",
)

FAKE_SCENES = [SceneDTO(index=0, start=0.0, end=15.0), SceneDTO(index=1, start=15.0, end=30.0)]

FAKE_ANALYSIS = AnalysisDTO(
    summary="A short test video.",
    suggested_title="Testing Rocks",
    suggested_description="A quick demo.",
    suggested_hashtags=["#test", "#demo"],
    highlights=[
        HighlightDTO(
            rank=1,
            start=2.0,
            end=6.0,
            rationale="Clear hook.",
            score=0.9,
            suggested_clip_title="The Hook",
        )
    ],
    provider="ollama",
    model="qwen2.5:3b",
    raw_response={"raw_text": "{}"},
)


def test_full_pipeline_runs_end_to_end_and_completes():
    user = UserFactory()
    uploaded = SimpleUploadedFile("clip.mp4", b"fake-bytes", content_type="video/mp4")

    with (
        patch("apps.videos.tasks.probe", return_value=FAKE_METADATA),
        patch("apps.transcripts.tasks.get_stt_provider") as mock_stt,
        patch("apps.highlights.tasks.get_llm_provider") as mock_llm,
        patch("apps.scenes.tasks.PySceneDetectProvider.detect", return_value=FAKE_SCENES),
    ):
        mock_stt.return_value.transcribe.return_value = FAKE_TRANSCRIPT
        mock_llm.return_value.generate_analysis.return_value = FAKE_ANALYSIS

        video = create_video_and_launch_pipeline(owner=user, uploaded_file=uploaded)

    video.refresh_from_db()

    assert video.status == UploadedVideo.Status.COMPLETED
    assert video.progress_percent == 100
    assert all(step_status == "done" for step_status in video.pipeline_steps.values())

    assert video.duration_seconds == 30.0
    assert video.transcript.segments.count() == 2
    assert video.scenes.count() == 2
    assert video.analysis_result.suggested_title == "Testing Rocks"
    assert video.analysis_result.highlights.count() == 1


def test_pipeline_stops_and_marks_failed_when_transcription_fails_permanently():
    from domain.exceptions import PermanentPipelineError

    user = UserFactory()
    uploaded = SimpleUploadedFile("clip.mp4", b"fake-bytes", content_type="video/mp4")

    with (
        patch("apps.videos.tasks.probe", return_value=FAKE_METADATA),
        patch("apps.transcripts.tasks.get_stt_provider") as mock_stt,
        patch("apps.scenes.tasks.PySceneDetectProvider.detect", return_value=FAKE_SCENES),
    ):
        mock_stt.return_value.transcribe.side_effect = PermanentPipelineError("unreadable audio")

        # Under CELERY_TASK_ALWAYS_EAGER (test settings), apply_async() runs
        # the whole graph synchronously and re-raises a failing task's
        # exception to the caller. In production (a real broker/worker) this
        # exception never reaches the upload view — it's only ever seen by
        # the worker, and the video's DB state is what callers rely on. The
        # task has already recorded the failure via fail_pipeline() before
        # re-raising, so we still assert on that DB state below.
        with pytest.raises(PermanentPipelineError, match="unreadable audio"):
            create_video_and_launch_pipeline(owner=user, uploaded_file=uploaded)

    video = UploadedVideo.objects.get(project__owner=user)
    assert video.status == UploadedVideo.Status.FAILED
    assert video.pipeline_steps["transcript"] == "failed"
    assert "unreadable audio" in video.error_message
    # The chord callback never runs because a group member failed — no
    # analysis result should have been created.
    assert not hasattr(video, "analysis_result")
