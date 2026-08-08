import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from domain.ai.providers.openrouter_provider import OpenRouterProvider
from domain.exceptions import TransientProviderError
from domain.scene_detection.base import SceneDTO
from domain.transcription.base import TranscriptionResult, TranscriptSegmentDTO


def _payload_with_highlights(count: int) -> dict:
    """A single-highlight payload against DEFAULT_NUM_HIGHLIGHTS (3) would
    spuriously trigger generate_analysis_with_repair's count-repair path
    (an extra httpx.post call the assertions below don't expect) — build a
    payload with exactly as many highlights as the test's num_highlights.
    """
    return {
        "summary": "Summary.",
        "suggested_title": "Title",
        "suggested_description": "Desc",
        "suggested_hashtags": ["#a"],
        "highlights": [
            {
                "rank": i + 1,
                "start": float(i * 5),
                "end": float(i * 5 + 4),
                "rationale": "r",
                "score": 0.5,
                "suggested_clip_title": "c",
            }
            for i in range(count)
        ],
    }


VALID_PAYLOAD = _payload_with_highlights(3)  # matches DEFAULT_NUM_HIGHLIGHTS


def _transcript():
    return TranscriptionResult(
        language="en",
        language_confidence=0.9,
        full_text="hi",
        segments=[TranscriptSegmentDTO(index=0, start=0.0, end=1.0, text="hi")],
        provider="faster_whisper",
        model="small",
    )


def test_requires_api_key():
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider(api_key="")


def test_generate_analysis_success():
    provider = OpenRouterProvider(api_key="sk-test", model="some/model")
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(VALID_PAYLOAD)}}]
    }

    with patch("httpx.post", return_value=fake_response) as mock_post:
        dto = provider.generate_analysis(
            transcript=_transcript(),
            scenes=[SceneDTO(index=0, start=0.0, end=5.0)],
            video_duration=5.0,
        )

    assert dto.suggested_title == "Title"
    assert dto.provider == "openrouter"
    mock_post.assert_called_once()  # count matched -- no repair round needed
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-test"
    assert mock_post.call_args.kwargs["json"]["temperature"] == 0.5  # DEFAULT_TEMPERATURE


def test_generate_analysis_passes_custom_num_highlights_and_temperature():
    provider = OpenRouterProvider(api_key="sk-test")
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(_payload_with_highlights(2))}}]
    }

    with patch("httpx.post", return_value=fake_response) as mock_post:
        provider.generate_analysis(
            transcript=_transcript(), scenes=[], video_duration=5.0,
            num_highlights=2, temperature=0.2,
        )  # fmt: skip

    mock_post.assert_called_once()  # count matched -- no repair round needed
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["temperature"] == 0.2
    user_prompt = call_kwargs["json"]["messages"][1]["content"]
    assert "EXACTLY 2 highlight-worthy moments" in user_prompt


def test_generate_analysis_passes_export_mode_full_video_asks_for_zero_highlights():
    provider = OpenRouterProvider(api_key="sk-test")
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(_payload_with_highlights(0))}}]
    }

    with patch("httpx.post", return_value=fake_response) as mock_post:
        provider.generate_analysis(
            transcript=_transcript(), scenes=[], video_duration=5.0, export_mode="full_video"
        )

    mock_post.assert_called_once()
    user_prompt = mock_post.call_args.kwargs["json"]["messages"][1]["content"]
    assert '"highlights": []' in user_prompt
    assert "EXACTLY" not in user_prompt


def test_generate_analysis_raises_transient_on_http_error():
    provider = OpenRouterProvider(api_key="sk-test")
    with (
        patch("httpx.post", side_effect=httpx.ConnectError("boom")),
        pytest.raises(TransientProviderError),
    ):
        provider.generate_analysis(transcript=_transcript(), scenes=[], video_duration=5.0)
