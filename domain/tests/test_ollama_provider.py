import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from domain.ai.providers.ollama_provider import OllamaProvider
from domain.exceptions import (
    PermanentPipelineError,
    ProviderResponseParseError,
    TransientProviderError,
)
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


def test_generate_analysis_success():
    provider = OllamaProvider(base_url="http://localhost:11434", model="qwen2.5:3b")
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"message": {"content": json.dumps(VALID_PAYLOAD)}}

    with patch("httpx.post", return_value=fake_response) as mock_post:
        dto = provider.generate_analysis(
            transcript=_transcript(),
            scenes=[SceneDTO(index=0, start=0.0, end=5.0)],
            video_duration=5.0,
        )

    assert dto.suggested_title == "Title"
    assert dto.provider == "ollama"
    mock_post.assert_called_once()  # count matched -- no repair round needed
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["model"] == "qwen2.5:3b"
    assert call_kwargs["json"]["options"]["temperature"] == 0.5  # DEFAULT_TEMPERATURE


def test_generate_analysis_passes_custom_num_highlights_and_temperature():
    provider = OllamaProvider()
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "message": {"content": json.dumps(_payload_with_highlights(7))}
    }

    with patch("httpx.post", return_value=fake_response) as mock_post:
        provider.generate_analysis(
            transcript=_transcript(), scenes=[], video_duration=5.0,
            num_highlights=7, temperature=0.9,
        )  # fmt: skip

    mock_post.assert_called_once()  # count matched -- no repair round needed
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["options"]["temperature"] == 0.9
    user_prompt = call_kwargs["json"]["messages"][1]["content"]
    assert "EXACTLY 7 highlight-worthy moments" in user_prompt


def test_generate_analysis_passes_export_mode_full_video_asks_for_zero_highlights():
    provider = OllamaProvider()
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "message": {"content": json.dumps(_payload_with_highlights(0))}
    }

    with patch("httpx.post", return_value=fake_response) as mock_post:
        provider.generate_analysis(
            transcript=_transcript(), scenes=[], video_duration=5.0, export_mode="full_video"
        )

    mock_post.assert_called_once()  # zero highlights matches the zero target -- no repair
    user_prompt = mock_post.call_args.kwargs["json"]["messages"][1]["content"]
    assert '"highlights": []' in user_prompt
    assert "EXACTLY" not in user_prompt


def test_generate_analysis_raises_transient_on_connection_error():
    provider = OllamaProvider()
    with (
        patch("httpx.post", side_effect=httpx.ConnectError("connection refused")),
        pytest.raises(TransientProviderError),
    ):
        provider.generate_analysis(transcript=_transcript(), scenes=[], video_duration=5.0)


def test_generate_analysis_raises_transient_on_timeout():
    provider = OllamaProvider()
    with (
        patch("httpx.post", side_effect=httpx.TimeoutException("timed out")),
        pytest.raises(TransientProviderError),
    ):
        provider.generate_analysis(transcript=_transcript(), scenes=[], video_duration=5.0)


def test_generate_analysis_raises_permanent_on_model_not_found():
    """Regression test: this is the exact production bug — a model that
    was never `ollama pull`ed returns 404, which must fail fast (Permanent)
    rather than burn through retries for a condition retrying can't fix.
    """
    provider = OllamaProvider(model="qwen2.5:3b")
    fake_response = MagicMock()
    fake_response.status_code = 404
    fake_response.text = "model 'qwen2.5:3b' not found, try pulling it first"
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=fake_response
    )

    with (
        patch("httpx.post", return_value=fake_response),
        pytest.raises(PermanentPipelineError, match="ollama-pull"),
    ):
        provider.generate_analysis(transcript=_transcript(), scenes=[], video_duration=5.0)


def test_generate_analysis_raises_transient_on_server_error():
    provider = OllamaProvider()
    fake_response = MagicMock()
    fake_response.status_code = 503
    fake_response.text = "service unavailable"
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503", request=MagicMock(), response=fake_response
    )

    with (
        patch("httpx.post", return_value=fake_response),
        pytest.raises(TransientProviderError),
    ):
        provider.generate_analysis(transcript=_transcript(), scenes=[], video_duration=5.0)


def test_generate_analysis_raises_parse_error_on_bad_response_shape():
    provider = OllamaProvider()
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"unexpected": "shape"}

    with (
        patch("httpx.post", return_value=fake_response),
        pytest.raises(ProviderResponseParseError),
    ):
        provider.generate_analysis(transcript=_transcript(), scenes=[], video_duration=5.0)
