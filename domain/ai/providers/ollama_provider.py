"""Local LLM provider using Ollama's chat API — the default AI_LLM_PROVIDER
for local-first analysis (summary/title/description/hashtags/highlights).
"""

from typing import ClassVar

import httpx

from domain.ai.base import AnalysisDTO, LLMProvider
from domain.ai.defaults import DEFAULT_NUM_HIGHLIGHTS, DEFAULT_TEMPERATURE
from domain.ai.prompts.highlight_extraction import (
    ChatMessages,
    generate_analysis_with_repair,
    schema_to_dto,
)
from domain.ai.providers.http_utils import classify_http_status_error
from domain.exceptions import ProviderResponseParseError, TransientProviderError
from domain.scene_detection.base import SceneDTO
from domain.transcription.base import TranscriptionResult


class OllamaProvider(LLMProvider):
    name: ClassVar[str] = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate_analysis(
        self,
        *,
        transcript: TranscriptionResult,
        scenes: list[SceneDTO],
        video_duration: float,
        num_highlights: int = DEFAULT_NUM_HIGHLIGHTS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> AnalysisDTO:
        schema, raw = generate_analysis_with_repair(
            send_chat=lambda messages: self._send_chat(messages, temperature=temperature),
            transcript=transcript,
            scenes=scenes,
            video_duration=video_duration,
            num_highlights=num_highlights,
        )
        return schema_to_dto(schema, provider=self.name, model=self.model, raw_text=raw)

    def _send_chat(self, messages: ChatMessages, *, temperature: float) -> str:
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": temperature},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TransientProviderError(f"Ollama request timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise classify_http_status_error(
                exc,
                provider_name="Ollama",
                hint=(
                    f"Is model {self.model!r} pulled? Run `make ollama-pull` "
                    f"(or `docker compose exec ollama ollama pull {self.model}`)."
                ),
            ) from exc
        except httpx.HTTPError as exc:
            # Connection errors — Ollama not running, still starting up, etc.
            raise TransientProviderError(f"Ollama request failed: {exc}") from exc

        try:
            return response.json()["message"]["content"]
        except (KeyError, ValueError) as exc:
            raise ProviderResponseParseError(f"Unexpected Ollama response shape: {exc}") from exc
