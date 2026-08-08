from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from domain.ai.defaults import DEFAULT_NUM_HIGHLIGHTS, DEFAULT_TEMPERATURE
from domain.scene_detection.base import SceneDTO
from domain.transcription.base import TranscriptionResult


@dataclass(frozen=True)
class HighlightDTO:
    rank: int
    start: float
    end: float
    rationale: str
    score: float | None
    suggested_clip_title: str | None


@dataclass(frozen=True)
class AnalysisDTO:
    summary: str
    suggested_title: str
    suggested_description: str
    suggested_hashtags: list[str]
    highlights: list[HighlightDTO]
    provider: str
    model: str
    raw_response: dict


class LLMProvider(ABC):
    """Interface every highlight-extraction / summarization backend must
    implement. Implementations live in `domain/ai/providers/` and are
    registered in `domain/ai/registry.py`'s LLM_PROVIDERS mapping.

    `num_highlights` and `temperature` are user-configurable via
    `apps.export_settings.models.ExportSettings` — new providers must
    accept both (ignoring `temperature` if the backend has no equivalent
    is fine; ignoring `num_highlights` is not, since it changes what the
    prompt itself asks for). See docs/ai_pipeline.md.
    """

    name: ClassVar[str]

    @abstractmethod
    def generate_analysis(
        self,
        *,
        transcript: TranscriptionResult,
        scenes: list[SceneDTO],
        video_duration: float,
        num_highlights: int = DEFAULT_NUM_HIGHLIGHTS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> AnalysisDTO:
        raise NotImplementedError


class ImageGenProvider(ABC):
    """Interface for future local/hosted image generation (Stable
    Diffusion/Flux) — declared now so the capability is modeled in the
    plugin architecture, but intentionally has no implementation or
    registry entry in phase 1. See docs/roadmap.md.
    """

    name: ClassVar[str]

    @abstractmethod
    def generate_image(self, *, prompt: str, width: int, height: int) -> bytes:
        raise NotImplementedError
