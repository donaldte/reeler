"""Shared HTTP error classification for LLM providers.

A 4xx response is (almost always) a permanent misconfiguration — wrong
model name, invalid API key, malformed request — that retrying will never
fix (this is exactly what happened in production: Ollama returning 404
because the configured model was never pulled kept getting retried for
several minutes before finally failing). 429 is the one exception: rate
limiting is inherently transient. 5xx and network-level failures (caught
separately by callers as httpx.TimeoutException / httpx.HTTPError) are
transient too.
"""

import httpx

from domain.exceptions import PermanentPipelineError, TransientProviderError


def classify_http_status_error(
    exc: httpx.HTTPStatusError, *, provider_name: str, hint: str = ""
) -> PermanentPipelineError | TransientProviderError:
    status = exc.response.status_code
    body_excerpt = exc.response.text[:300]
    if 400 <= status < 500 and status != 429:
        message = f"{provider_name} rejected the request ({status}): {body_excerpt}"
        if hint:
            message = f"{message} {hint}"
        return PermanentPipelineError(message)
    return TransientProviderError(f"{provider_name} error ({status}): {body_excerpt}")
