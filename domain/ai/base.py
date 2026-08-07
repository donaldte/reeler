from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

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
    """

    name: ClassVar[str]

    @abstractmethod
    def generate_analysis(
        self,
        *,
        transcript: TranscriptionResult,
        scenes: list[SceneDTO],
        video_duration: float,
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
