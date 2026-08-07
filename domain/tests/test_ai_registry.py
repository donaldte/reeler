from types import SimpleNamespace

import pytest

from domain.ai.providers.ollama_provider import OllamaProvider
from domain.ai.providers.openrouter_provider import OpenRouterProvider
from domain.ai.registry import get_llm_provider, get_stt_provider
from domain.transcription.providers.faster_whisper_provider import FasterWhisperProvider


def _settings(**overrides):
    base = {
        "AI_STT_PROVIDER": "faster_whisper",
        "AI_STT_PROVIDER_KWARGS": {"faster_whisper": {"model_size": "tiny"}},
        "AI_LLM_PROVIDER": "ollama",
        "AI_LLM_PROVIDER_KWARGS": {
            "ollama": {"model": "qwen2.5:3b"},
            "openrouter": {"api_key": "sk-test", "model": "some/model"},
        },
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_get_stt_provider_returns_configured_implementation():
    provider = get_stt_provider(_settings())
    assert isinstance(provider, FasterWhisperProvider)
    assert provider.model_size == "tiny"


def test_get_llm_provider_defaults_to_ollama():
    provider = get_llm_provider(_settings())
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "qwen2.5:3b"


def test_get_llm_provider_can_select_openrouter():
    provider = get_llm_provider(_settings(AI_LLM_PROVIDER="openrouter"))
    assert isinstance(provider, OpenRouterProvider)
    assert provider.api_key == "sk-test"


def test_get_stt_provider_raises_on_unknown_key():
    with pytest.raises(ValueError, match="Unknown AI_STT_PROVIDER"):
        get_stt_provider(_settings(AI_STT_PROVIDER="does-not-exist"))


def test_get_llm_provider_raises_on_unknown_key():
    with pytest.raises(ValueError, match="Unknown AI_LLM_PROVIDER"):
        get_llm_provider(_settings(AI_LLM_PROVIDER="does-not-exist"))
