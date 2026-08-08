from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from domain.ai.defaults import DEFAULT_EXPORT_MODE, DEFAULT_NUM_HIGHLIGHTS, DEFAULT_TEMPERATURE
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
    emoji: str | None = None
    transition: str | None = None


@dataclass(frozen=True)
class BrollSuggestionDTO:
    start: float
    end: float
    query: str


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
    broll_suggestions: list[BrollSuggestionDTO] = field(default_factory=list)


class LLMProvider(ABC):
    """Interface every highlight-extraction / summarization backend must
    implement. Implementations live in `domain/ai/providers/` and are
    registered in `domain/ai/registry.py`'s LLM_PROVIDERS mapping.

    `num_highlights`, `temperature`, and `export_mode` are all
    user-configurable via `apps.export_settings.models.ExportSettings` —
    new providers must accept all three (ignoring `temperature` if the
    backend has no equivalent is fine; ignoring `num_highlights`/
    `export_mode` is not, since together they change what the prompt
    itself asks for -- see docs/ai_pipeline.md). `export_mode="full_video"`
    means the whole source video is kept, not cut into highlights, so
    `num_highlights` is not requested at all in that mode.
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
        export_mode: str = DEFAULT_EXPORT_MODE,
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
