from unittest.mock import MagicMock, patch

import httpx
import pytest

from domain.exceptions import (
    PermanentPipelineError,
    ProviderResponseParseError,
    TransientProviderError,
)
from domain.stock_media.providers.pexels_provider import PexelsProvider

VALID_PAYLOAD = {
    "photos": [
        {
            "id": 12345,
            "width": 1920,
            "height": 1080,
            "url": "https://www.pexels.com/photo/12345/",
            "photographer": "Jane Doe",
            "src": {"large2x": "https://images.pexels.com/photos/12345/large2x.jpg"},
        }
    ]
}


def test_requires_api_key():
    with pytest.raises(ValueError, match="PEXELS_API_KEY"):
        PexelsProvider(api_key="")


def test_search_media_success():
    provider = PexelsProvider(api_key="test-key")
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = VALID_PAYLOAD

    with patch("httpx.get", return_value=fake_response) as mock_get:
        results = provider.search_media(query="laptop coding")

    assert len(results) == 1
    assert results[0].id == "12345"
    assert results[0].image_url == "https://images.pexels.com/photos/12345/large2x.jpg"
    assert results[0].photographer == "Jane Doe"
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "test-key"  # raw key, not "Bearer "
    assert call_kwargs["params"]["query"] == "laptop coding"


def test_search_media_empty_results():
    provider = PexelsProvider(api_key="test-key")
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"photos": []}

    with patch("httpx.get", return_value=fake_response):
        results = provider.search_media(query="nonexistent thing")

    assert results == []


def test_search_media_raises_transient_on_timeout():
    provider = PexelsProvider(api_key="test-key")
    with (
        patch("httpx.get", side_effect=httpx.TimeoutException("timed out")),
        pytest.raises(TransientProviderError),
    ):
        provider.search_media(query="x")


def test_search_media_raises_transient_on_connection_error():
    provider = PexelsProvider(api_key="test-key")
    with (
        patch("httpx.get", side_effect=httpx.ConnectError("refused")),
        pytest.raises(TransientProviderError),
    ):
        provider.search_media(query="x")


def test_search_media_raises_permanent_on_bad_api_key():
    provider = PexelsProvider(api_key="bad-key")
    fake_response = MagicMock()
    fake_response.status_code = 401
    fake_response.text = "Unauthorized"
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401", request=MagicMock(), response=fake_response
    )

    with (
        patch("httpx.get", return_value=fake_response),
        pytest.raises(PermanentPipelineError, match="PEXELS_API_KEY"),
    ):
        provider.search_media(query="x")


def test_search_media_raises_transient_on_rate_limit():
    provider = PexelsProvider(api_key="test-key")
    fake_response = MagicMock()
    fake_response.status_code = 429
    fake_response.text = "Too Many Requests"
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "429", request=MagicMock(), response=fake_response
    )

    with (
        patch("httpx.get", return_value=fake_response),
        pytest.raises(TransientProviderError),
    ):
        provider.search_media(query="x")


def test_search_media_raises_parse_error_on_bad_response_shape():
    provider = PexelsProvider(api_key="test-key")
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"unexpected": "shape"}

    with (
        patch("httpx.get", return_value=fake_response),
        pytest.raises(ProviderResponseParseError),
    ):
        provider.search_media(query="x")
