from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class TranscriptSegmentDTO:
    index: int
    start: float
    end: float
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    language: str
    language_confidence: float | None
    full_text: str
    segments: list[TranscriptSegmentDTO]
    provider: str
    model: str


class SpeechToTextProvider(ABC):
    """Interface every speech-to-text backend must implement.

    Implementations live in `domain/transcription/providers/` and are
    registered in `domain/ai/registry.py`'s STT_PROVIDERS mapping. See
    docs/ai_pipeline.md for how to add a new one.
    """

    name: ClassVar[str]

    @abstractmethod
    def transcribe(self, audio_path: Path, *, language: str | None = None) -> TranscriptionResult:
        """Transcribe the audio/video at `audio_path`.

        Args:
            audio_path: path to a local media file ffmpeg/whisper can read.
            language: optional ISO 639-1 hint; None lets the provider
                auto-detect (the detected language is always returned on
                the result regardless of whether a hint was given).
        """
        raise NotImplementedError
