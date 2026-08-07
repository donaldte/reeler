import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from domain.transcription.providers.faster_whisper_provider import FasterWhisperProvider


def _fake_segment(index: int, start: float, end: float, text: str, avg_logprob: float = -0.1):
    return SimpleNamespace(start=start, end=end, text=text, avg_logprob=avg_logprob)


def test_transcribe_maps_segments_and_info(tmp_path):
    provider = FasterWhisperProvider(model_size="tiny", device="cpu", compute_type="int8")

    fake_segments = [
        _fake_segment(0, 0.0, 1.5, "Hello there."),
        _fake_segment(1, 1.5, 3.0, "General Kenobi."),
    ]
    fake_info = SimpleNamespace(language="en", language_probability=0.98)

    fake_model = MagicMock()
    fake_model.transcribe.return_value = (iter(fake_segments), fake_info)

    with patch.object(FasterWhisperProvider, "_get_model", return_value=fake_model):
        result = provider.transcribe(tmp_path / "clip.mp4")

    assert result.language == "en"
    assert result.language_confidence == 0.98
    assert result.full_text == "Hello there. General Kenobi."
    assert result.provider == "faster_whisper"
    assert result.model == "tiny"
    assert len(result.segments) == 2
    assert result.segments[0].text == "Hello there."
    assert result.segments[0].confidence == round(math.exp(-0.1), 4)


def test_model_is_lazily_constructed():
    provider = FasterWhisperProvider()
    assert provider._model is None
