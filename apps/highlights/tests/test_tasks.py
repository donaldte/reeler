from unittest.mock import MagicMock, patch

import pytest

from apps.export_settings.models import ExportSettings
from apps.export_settings.tests.factories import ExportSettingsFactory
from apps.highlights.models import AnalysisResult
from apps.highlights.tasks import generate_analysis_task
from apps.scenes.models import Scene
from apps.transcripts.models import Transcript, TranscriptSegment
from apps.videos.constants import PIPELINE_STEP_ANALYSIS, STEP_DONE
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory
from domain.ai.base import AnalysisDTO, HighlightDTO

pytestmark = pytest.mark.django_db


def _video_with_transcript_and_scenes():
    video = UploadedVideoFactory(duration_seconds=30.0)
    transcript = Transcript.objects.create(
        video=video,
        language="en",
        language_confidence=0.9,
        full_text="hi",
        provider="faster_whisper",
        model_name="small",
    )
    TranscriptSegment.objects.create(
        transcript=transcript, index=0, start_time=0.0, end_time=2.0, text="hi"
    )
    Scene.objects.create(video=video, index=0, start_time=0.0, end_time=30.0)
    return video


FAKE_ANALYSIS = AnalysisDTO(
    summary="Summary",
    suggested_title="Title",
    suggested_description="Desc",
    suggested_hashtags=["#a", "#b"],
    highlights=[
        HighlightDTO(
            rank=1,
            start=0.0,
            end=5.0,
            rationale="r",
            score=0.8,
            suggested_clip_title="c",
            emoji="🔥",
            transition="cut",
        ),
    ],
    provider="ollama",
    model="qwen2.5:3b",
    raw_response={"raw_text": "{}"},
)


def test_generate_analysis_task_persists_result_and_highlights():
    video = _video_with_transcript_and_scenes()
    fake_provider = MagicMock()
    fake_provider.generate_analysis.return_value = FAKE_ANALYSIS

    with patch("apps.highlights.tasks.get_llm_provider", return_value=fake_provider):
        generate_analysis_task(str(video.id))

    result = AnalysisResult.objects.get(video=video)
    assert result.suggested_title == "Title"
    assert result.highlights.count() == 1
    highlight = result.highlights.get()
    assert highlight.emoji == "🔥"
    assert highlight.transition == "cut"
    video.refresh_from_db()
    assert video.status == UploadedVideo.Status.COMPLETED
    assert video.progress_percent == 100
    assert video.pipeline_steps[PIPELINE_STEP_ANALYSIS] == STEP_DONE


def test_generate_analysis_task_passes_reconstructed_transcript_and_scenes():
    video = _video_with_transcript_and_scenes()
    fake_provider = MagicMock()
    fake_provider.generate_analysis.return_value = FAKE_ANALYSIS

    with patch("apps.highlights.tasks.get_llm_provider", return_value=fake_provider):
        generate_analysis_task(str(video.id))

    call_kwargs = fake_provider.generate_analysis.call_args.kwargs
    assert call_kwargs["transcript"].full_text == "hi"
    assert len(call_kwargs["scenes"]) == 1
    assert call_kwargs["video_duration"] == 30.0


def test_generate_analysis_task_uses_video_export_settings():
    video = _video_with_transcript_and_scenes()
    ExportSettingsFactory(
        video=video,
        num_highlights=7,
        ai_creativity_level=ExportSettings.AiCreativityLevel.CREATIVE,
    )
    fake_provider = MagicMock()
    fake_provider.generate_analysis.return_value = FAKE_ANALYSIS

    with patch("apps.highlights.tasks.get_llm_provider", return_value=fake_provider):
        generate_analysis_task(str(video.id))

    call_kwargs = fake_provider.generate_analysis.call_args.kwargs
    assert call_kwargs["num_highlights"] == 7
    assert call_kwargs["temperature"] == 0.9  # CREATIVE


def test_generate_analysis_task_uses_default_settings_when_none_saved():
    video = _video_with_transcript_and_scenes()
    fake_provider = MagicMock()
    fake_provider.generate_analysis.return_value = FAKE_ANALYSIS

    with patch("apps.highlights.tasks.get_llm_provider", return_value=fake_provider):
        generate_analysis_task(str(video.id))

    call_kwargs = fake_provider.generate_analysis.call_args.kwargs
    assert call_kwargs["num_highlights"] == 3  # ExportSettings default
    assert call_kwargs["temperature"] == 0.5  # BALANCED default
