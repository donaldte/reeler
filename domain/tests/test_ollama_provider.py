import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from domain.ai.providers.ollama_provider import OllamaProvider
from domain.exceptions import ProviderResponseParseError, TransientProviderError
from domain.scene_detection.base import SceneDTO
from domain.transcription.base import TranscriptionResult, TranscriptSegmentDTO

VALID_PAYLOAD = {
    "summary": "Summary.",
    "suggested_title": "Title",
    "suggested_description": "Desc",
    "suggested_hashtags": ["#a"],
    "highlights": [
        {
            "rank": 1,
            "start": 0.0,
            "end": 5.0,
            "rationale": "r",
            "score": 0.5,
            "suggested_clip_title": "c",
        }
    ],
}


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
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["model"] == "qwen2.5:3b"


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
