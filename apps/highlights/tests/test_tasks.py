from unittest.mock import MagicMock, patch

import httpx
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
from domain.ai.base import AnalysisDTO, BrollSuggestionDTO, HighlightDTO
from domain.exceptions import TransientProviderError
from domain.stock_media.base import StockMediaResultDTO

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


FAKE_ANALYSIS_WITH_BROLL = AnalysisDTO(
    summary=FAKE_ANALYSIS.summary,
    suggested_title=FAKE_ANALYSIS.suggested_title,
    suggested_description=FAKE_ANALYSIS.suggested_description,
    suggested_hashtags=FAKE_ANALYSIS.suggested_hashtags,
    highlights=FAKE_ANALYSIS.highlights,
    broll_suggestions=[
        BrollSuggestionDTO(start=1.0, end=3.0, query="laptop coding"),
        BrollSuggestionDTO(start=10.0, end=12.0, query="coffee cup"),
    ],
    provider=FAKE_ANALYSIS.provider,
    model=FAKE_ANALYSIS.model,
    raw_response=FAKE_ANALYSIS.raw_response,
)


def _fake_stock_result(image_id: str) -> StockMediaResultDTO:
    return StockMediaResultDTO(
        id=image_id,
        image_url=f"https://images.example/{image_id}.jpg",
        width=1920,
        height=1080,
        photographer="Jane Doe",
        source_page_url=f"https://example/{image_id}",
    )


def test_generate_analysis_task_fetches_broll_assets_when_stock_footage_enabled():
    video = _video_with_transcript_and_scenes()
    ExportSettingsFactory(video=video, broll_type=ExportSettings.BrollType.STOCK_FOOTAGE)
    fake_llm = MagicMock()
    fake_llm.generate_analysis.return_value = FAKE_ANALYSIS_WITH_BROLL
    fake_stock_provider = MagicMock()
    fake_stock_provider.name = "pexels"
    fake_stock_provider.search_media.side_effect = [
        [_fake_stock_result("1")],
        [_fake_stock_result("2")],
    ]
    fake_image_response = MagicMock(content=b"fake-image-bytes")
    fake_image_response.raise_for_status.return_value = None

    with (
        patch("apps.highlights.tasks.get_llm_provider", return_value=fake_llm),
        patch("apps.highlights.tasks.get_stock_media_provider", return_value=fake_stock_provider),
        patch("apps.highlights.tasks.httpx.get", return_value=fake_image_response),
    ):
        generate_analysis_task(str(video.id))

    result = AnalysisResult.objects.get(video=video)
    assert result.broll_assets.count() == 2
    asset = result.broll_assets.get(query="laptop coding")
    assert asset.start_time == 1.0
    assert asset.end_time == 3.0
    assert asset.source_provider == "pexels"
    assert asset.source_id == "1"
    assert asset.image


def test_generate_analysis_task_skips_broll_fetch_when_type_is_none():
    video = _video_with_transcript_and_scenes()
    # broll_type defaults to "none" -- no ExportSettingsFactory override
    fake_llm = MagicMock()
    fake_llm.generate_analysis.return_value = FAKE_ANALYSIS_WITH_BROLL

    with (
        patch("apps.highlights.tasks.get_llm_provider", return_value=fake_llm),
        patch("apps.highlights.tasks.get_stock_media_provider") as mock_get_provider,
    ):
        generate_analysis_task(str(video.id))

    mock_get_provider.assert_not_called()
    result = AnalysisResult.objects.get(video=video)
    assert result.broll_assets.count() == 0


def test_generate_analysis_task_completes_even_when_stock_media_provider_unconfigured():
    """No PEXELS_API_KEY configured -> get_stock_media_provider raises
    ValueError -- must not turn a successful analysis into a FAILED video.
    """
    video = _video_with_transcript_and_scenes()
    ExportSettingsFactory(video=video, broll_type=ExportSettings.BrollType.STOCK_FOOTAGE)
    fake_llm = MagicMock()
    fake_llm.generate_analysis.return_value = FAKE_ANALYSIS_WITH_BROLL

    with (
        patch("apps.highlights.tasks.get_llm_provider", return_value=fake_llm),
        patch(
            "apps.highlights.tasks.get_stock_media_provider",
            side_effect=ValueError("PEXELS_API_KEY is required"),
        ),
    ):
        generate_analysis_task(str(video.id))

    video.refresh_from_db()
    assert video.status == UploadedVideo.Status.COMPLETED
    result = AnalysisResult.objects.get(video=video)
    assert result.broll_assets.count() == 0


def test_generate_analysis_task_skips_one_broll_suggestion_on_search_failure_keeps_others():
    video = _video_with_transcript_and_scenes()
    ExportSettingsFactory(video=video, broll_type=ExportSettings.BrollType.STOCK_FOOTAGE)
    fake_llm = MagicMock()
    fake_llm.generate_analysis.return_value = FAKE_ANALYSIS_WITH_BROLL
    fake_stock_provider = MagicMock()
    fake_stock_provider.name = "pexels"
    fake_stock_provider.search_media.side_effect = [
        TransientProviderError("rate limited"),
        [_fake_stock_result("2")],
    ]
    fake_image_response = MagicMock(content=b"fake-image-bytes")
    fake_image_response.raise_for_status.return_value = None

    with (
        patch("apps.highlights.tasks.get_llm_provider", return_value=fake_llm),
        patch("apps.highlights.tasks.get_stock_media_provider", return_value=fake_stock_provider),
        patch("apps.highlights.tasks.httpx.get", return_value=fake_image_response),
    ):
        generate_analysis_task(str(video.id))

    result = AnalysisResult.objects.get(video=video)
    assert result.broll_assets.count() == 1
    assert result.broll_assets.get().query == "coffee cup"


def test_generate_analysis_task_skips_broll_suggestion_when_image_download_fails():
    video = _video_with_transcript_and_scenes()
    ExportSettingsFactory(video=video, broll_type=ExportSettings.BrollType.STOCK_FOOTAGE)
    fake_llm = MagicMock()
    fake_llm.generate_analysis.return_value = FAKE_ANALYSIS_WITH_BROLL
    fake_stock_provider = MagicMock()
    fake_stock_provider.name = "pexels"
    fake_stock_provider.search_media.return_value = [_fake_stock_result("1")]

    with (
        patch("apps.highlights.tasks.get_llm_provider", return_value=fake_llm),
        patch("apps.highlights.tasks.get_stock_media_provider", return_value=fake_stock_provider),
        patch("apps.highlights.tasks.httpx.get", side_effect=httpx.ConnectError("refused")),
    ):
        generate_analysis_task(str(video.id))

    video.refresh_from_db()
    assert video.status == UploadedVideo.Status.COMPLETED
    result = AnalysisResult.objects.get(video=video)
    assert result.broll_assets.count() == 0
