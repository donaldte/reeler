"""End-to-end test of the settings-change -> re-analysis path, without
mocking rerun_analysis_only itself (unlike test_services.py/test_api.py/
test_views.py, which mock it to keep those tests focused on their own
layer). Only the LLM provider is mocked — everything else, including
Celery's eager execution of generate_analysis_task, is real.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.export_settings.services import maybe_rerun_analysis
from apps.export_settings.tests.factories import ExportSettingsFactory
from apps.highlights.models import AnalysisResult
from apps.scenes.models import Scene
from apps.transcripts.models import Transcript, TranscriptSegment
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory
from domain.ai.base import AnalysisDTO, HighlightDTO

pytestmark = pytest.mark.django_db


def _completed_video_with_prior_analysis() -> UploadedVideo:
    video = UploadedVideoFactory(duration_seconds=30.0, status=UploadedVideo.Status.COMPLETED)
    transcript = Transcript.objects.create(
        video=video, language="en", language_confidence=0.9, full_text="hi",
        provider="faster_whisper", model_name="small",
    )  # fmt: skip
    TranscriptSegment.objects.create(
        transcript=transcript, index=0, start_time=0.0, end_time=2.0, text="hi"
    )
    Scene.objects.create(video=video, index=0, start_time=0.0, end_time=30.0)
    # A prior analysis result, as if the first automatic pass already ran.
    old_result = AnalysisResult.objects.create(
        video=video, summary="old", suggested_title="Old Title", suggested_description="old",
        suggested_hashtags=[], llm_provider="ollama", llm_model="qwen2.5:3b", raw_response={},
    )  # fmt: skip
    old_result.highlights.create(rank=1, start_time=0.0, end_time=1.0, rationale="old")
    return video


NEW_ANALYSIS = AnalysisDTO(
    summary="new summary",
    suggested_title="New Title",
    suggested_description="new desc",
    suggested_hashtags=["#new"],
    highlights=[
        HighlightDTO(
            rank=1, start=1.0, end=2.0, rationale="new", score=0.7, suggested_clip_title=None
        ),
        HighlightDTO(
            rank=2, start=3.0, end=4.0, rationale="new2", score=0.6, suggested_clip_title=None
        ),
    ],
    provider="ollama",
    model="qwen2.5:3b",
    raw_response={"raw_text": "{}"},
)


def test_changing_num_highlights_rerenders_analysis_end_to_end():
    video = _completed_video_with_prior_analysis()
    ExportSettingsFactory(video=video, num_highlights=2)

    fake_provider = MagicMock()
    fake_provider.generate_analysis.return_value = NEW_ANALYSIS

    with patch("apps.highlights.tasks.get_llm_provider", return_value=fake_provider):
        did_rerun = maybe_rerun_analysis(video, {"num_highlights"})

    assert did_rerun is True

    call_kwargs = fake_provider.generate_analysis.call_args.kwargs
    assert call_kwargs["num_highlights"] == 2

    result = AnalysisResult.objects.get(video=video)
    assert result.suggested_title == "New Title"  # old result was replaced, not duplicated
    assert result.highlights.count() == 2
    video.refresh_from_db()
    assert video.status == UploadedVideo.Status.COMPLETED


def test_changing_only_inert_field_does_not_touch_existing_analysis():
    video = _completed_video_with_prior_analysis()
    ExportSettingsFactory(video=video)

    fake_provider = MagicMock()
    fake_provider.generate_analysis.return_value = NEW_ANALYSIS

    with patch("apps.highlights.tasks.get_llm_provider", return_value=fake_provider):
        did_rerun = maybe_rerun_analysis(video, {"music_style"})

    assert did_rerun is False
    fake_provider.generate_analysis.assert_not_called()
    result = AnalysisResult.objects.get(video=video)
    assert result.suggested_title == "Old Title"  # untouched
