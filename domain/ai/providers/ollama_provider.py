"""Local LLM provider using Ollama's chat API — the default AI_LLM_PROVIDER
for local-first analysis (summary/title/description/hashtags/highlights).
"""

from typing import ClassVar

import httpx

from domain.ai.base import AnalysisDTO, LLMProvider
from domain.ai.prompts.highlight_extraction import (
    ChatMessages,
    generate_analysis_with_repair,
    schema_to_dto,
)
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
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TransientProviderError(f"Ollama request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            # Includes connection errors (Ollama not running/still loading the
            # model) and non-2xx responses — both are worth retrying.
            raise TransientProviderError(f"Ollama request failed: {exc}") from exc

        try:
            return response.json()["message"]["content"]
        except (KeyError, ValueError) as exc:
            raise ProviderResponseParseError(f"Unexpected Ollama response shape: {exc}") from exc
