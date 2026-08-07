"""Resolves which concrete provider implementation to use for each AI
capability, based on config passed in by the caller.

Deliberately takes a plain `settings`-like object (any object exposing the
right attributes) rather than importing `django.conf.settings` directly —
keeps `domain/` framework-free and this function trivially testable with a
plain namespace. Django Celery tasks pass in `django.conf.settings` itself.

To add a new provider: implement the relevant ABC in
`domain/<capability>/providers/your_provider.py`, register it in the
`*_PROVIDERS` dict below, and add its config keys to `.env.example` +
`AI_*_PROVIDER_KWARGS` in `config/settings/base.py`. See docs/ai_pipeline.md.
"""

from typing import Any, Protocol

from domain.ai.base import LLMProvider
from domain.ai.providers.ollama_provider import OllamaProvider
from domain.ai.providers.openrouter_provider import OpenRouterProvider
from domain.transcription.base import SpeechToTextProvider
from domain.transcription.providers.faster_whisper_provider import FasterWhisperProvider


class SettingsLike(Protocol):
    AI_STT_PROVIDER: str
    AI_STT_PROVIDER_KWARGS: dict[str, dict[str, Any]]
    AI_LLM_PROVIDER: str
    AI_LLM_PROVIDER_KWARGS: dict[str, dict[str, Any]]


STT_PROVIDERS: dict[str, type[SpeechToTextProvider]] = {
    "faster_whisper": FasterWhisperProvider,
}

LLM_PROVIDERS: dict[str, type[LLMProvider]] = {
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
}


def get_stt_provider(settings: SettingsLike) -> SpeechToTextProvider:
    key = settings.AI_STT_PROVIDER
    try:
        provider_cls = STT_PROVIDERS[key]
    except KeyError as exc:
        raise ValueError(
            f"Unknown AI_STT_PROVIDER={key!r}. Available: {sorted(STT_PROVIDERS)}"
        ) from exc
    kwargs = settings.AI_STT_PROVIDER_KWARGS.get(key, {})
    return provider_cls(**kwargs)


def get_llm_provider(settings: SettingsLike) -> LLMProvider:
    key = settings.AI_LLM_PROVIDER
    try:
        provider_cls = LLM_PROVIDERS[key]
    except KeyError as exc:
        raise ValueError(
            f"Unknown AI_LLM_PROVIDER={key!r}. Available: {sorted(LLM_PROVIDERS)}"
        ) from exc
    kwargs = settings.AI_LLM_PROVIDER_KWARGS.get(key, {})
    return provider_cls(**kwargs)
