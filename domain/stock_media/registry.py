"""Resolves which concrete stock-media provider to use, based on config
passed in by the caller. Identical shape to domain/ai/registry.py — see
that module's docstring for the full rationale (framework-free `domain/`,
plain settings-like Protocol, trivially testable).
"""

from typing import Any, Protocol

from domain.stock_media.base import StockMediaProvider
from domain.stock_media.providers.pexels_provider import PexelsProvider


class SettingsLike(Protocol):
    STOCK_MEDIA_PROVIDER: str
    STOCK_MEDIA_PROVIDER_KWARGS: dict[str, dict[str, Any]]


STOCK_MEDIA_PROVIDERS: dict[str, type[StockMediaProvider]] = {
    "pexels": PexelsProvider,
}


def get_stock_media_provider(settings: SettingsLike) -> StockMediaProvider:
    key = settings.STOCK_MEDIA_PROVIDER
    try:
        provider_cls = STOCK_MEDIA_PROVIDERS[key]
    except KeyError as exc:
        raise ValueError(
            f"Unknown STOCK_MEDIA_PROVIDER={key!r}. Available: {sorted(STOCK_MEDIA_PROVIDERS)}"
        ) from exc
    kwargs = settings.STOCK_MEDIA_PROVIDER_KWARGS.get(key, {})
    return provider_cls(**kwargs)
