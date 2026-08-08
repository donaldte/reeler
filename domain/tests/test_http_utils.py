from unittest.mock import MagicMock

import httpx
import pytest

from domain.ai.providers.http_utils import classify_http_status_error
from domain.exceptions import PermanentPipelineError, TransientProviderError


def _status_error(status_code: int, body: str = "not found") -> httpx.HTTPStatusError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = body
    return httpx.HTTPStatusError("boom", request=MagicMock(), response=response)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_4xx_except_429_is_permanent(status):
    exc = classify_http_status_error(_status_error(status), provider_name="Ollama")
    assert isinstance(exc, PermanentPipelineError)
    assert "Ollama rejected the request" in str(exc)


def test_429_is_transient_not_permanent():
    exc = classify_http_status_error(_status_error(429), provider_name="Ollama")
    assert isinstance(exc, TransientProviderError)


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_is_transient(status):
    exc = classify_http_status_error(_status_error(status), provider_name="OpenRouter")
    assert isinstance(exc, TransientProviderError)


def test_hint_is_appended_when_provided():
    exc = classify_http_status_error(
        _status_error(404), provider_name="Ollama", hint="Run `make ollama-pull`."
    )
    assert "Run `make ollama-pull`." in str(exc)


def test_no_hint_by_default():
    exc = classify_http_status_error(_status_error(404), provider_name="OpenRouter")
    assert "hint" not in str(exc).lower()
