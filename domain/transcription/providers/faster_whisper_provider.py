"""Local speech-to-text via faster-whisper (CTranslate2 Whisper reimplementation).

Chosen over stock openai-whisper for phase 1 because it's significantly
faster on CPU-only dev machines (int8 quantization) — see
docs/ai_pipeline.md for the full rationale and model-size trade-offs.
"""

import math
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from domain.transcription.base import (
    SpeechToTextProvider,
    TranscriptionResult,
    TranscriptSegmentDTO,
)

if TYPE_CHECKING:
    from faster_whisper import WhisperModel


class FasterWhisperProvider(SpeechToTextProvider):
    name: ClassVar[str] = "faster_whisper"

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        # lazy-loaded: keep provider construction cheap/side-effect-free
        self._model: WhisperModel | None = None

    def _get_model(self) -> "WhisperModel":
        if self._model is None:
            from faster_whisper import (
                WhisperModel,  # imported lazily: heavy, optional at import time
            )

            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> TranscriptionResult:
        model = self._get_model()
        segments_iter, info = model.transcribe(
            str(audio_path), language=language, vad_filter=True, word_timestamps=False
        )

        segments: list[TranscriptSegmentDTO] = []
        full_text_parts: list[str] = []
        for index, segment in enumerate(segments_iter):
            text = segment.text.strip()
            full_text_parts.append(text)
            segments.append(
                TranscriptSegmentDTO(
                    index=index,
                    start=segment.start,
                    end=segment.end,
                    text=text,
                    confidence=_avg_logprob_to_confidence(getattr(segment, "avg_logprob", None)),
                )
            )

        return TranscriptionResult(
            language=info.language,
            language_confidence=info.language_probability,
            full_text=" ".join(full_text_parts),
            segments=segments,
            provider=self.name,
            model=self.model_size,
        )


def _avg_logprob_to_confidence(avg_logprob: float | None) -> float | None:
    """Whisper doesn't emit a calibrated confidence score; `exp(avg_logprob)`
    is the conventional approximation used across Whisper-based tooling.
    """
    if avg_logprob is None:
        return None
    return round(min(1.0, math.exp(avg_logprob)), 4)
