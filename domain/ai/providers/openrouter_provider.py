"""Hosted LLM provider using OpenRouter's OpenAI-compatible chat completions
API — a pluggable alternative to the local-first Ollama default, useful when
higher-quality models or faster turnaround matter more than running fully
offline. Selected via AI_LLM_PROVIDER=openrouter.
"""

from typing import ClassVar

import httpx

from domain.ai.base import AnalysisDTO, LLMProvider
from domain.ai.prompts.highlight_extraction import (
    ChatMessages,
    generate_analysis_with_repair,
    schema_to_dto,
)
from domain.ai.providers.http_utils import classify_http_status_error
from domain.exceptions import ProviderResponseParseError, TransientProviderError
from domain.scene_detection.base import SceneDTO
from domain.transcription.base import TranscriptionResult


class OpenRouterProvider(LLMProvider):
    name: ClassVar[str] = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "meta-llama/llama-3.1-8b-instruct:free",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required when AI_LLM_PROVIDER=openrouter")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate_analysis(
        self, *, transcript: TranscriptionResult, scenes: list[SceneDTO], video_duration: float
    ) -> AnalysisDTO:
        schema, raw = generate_analysis_with_repair(
            send_chat=self._send_chat,
            transcript=transcript,
            scenes=scenes,
            video_duration=video_duration,
        )
        return schema_to_dto(schema, provider=self.name, model=self.model, raw_text=raw)

    def _send_chat(self, messages: ChatMessages) -> str:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://github.com/reeler-video/reeler",
                    "X-Title": "Reeler",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TransientProviderError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            hint = (
                "Check OPENROUTER_API_KEY / OPENROUTER_MODEL."
                if exc.response.status_code in (401, 404)
                else ""
            )
            raise classify_http_status_error(exc, provider_name="OpenRouter", hint=hint) from exc
        except httpx.HTTPError as exc:
            raise TransientProviderError(f"OpenRouter request failed: {exc}") from exc

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderResponseParseError(
                f"Unexpected OpenRouter response shape: {exc}"
            ) from exc
