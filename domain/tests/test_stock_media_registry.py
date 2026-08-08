from types import SimpleNamespace

import pytest

from domain.stock_media.providers.pexels_provider import PexelsProvider
from domain.stock_media.registry import get_stock_media_provider


def _settings(**overrides):
    base = {
        "STOCK_MEDIA_PROVIDER": "pexels",
        "STOCK_MEDIA_PROVIDER_KWARGS": {"pexels": {"api_key": "test-key"}},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_get_stock_media_provider_defaults_to_pexels():
    provider = get_stock_media_provider(_settings())
    assert isinstance(provider, PexelsProvider)
    assert provider.api_key == "test-key"


def test_get_stock_media_provider_raises_on_unknown_key():
    with pytest.raises(ValueError, match="Unknown STOCK_MEDIA_PROVIDER"):
        get_stock_media_provider(_settings(STOCK_MEDIA_PROVIDER="does-not-exist"))


def test_get_stock_media_provider_propagates_missing_api_key():
    # config/settings/base.py's PEXELS_API_KEY always defaults to "" (an
    # empty string, not an absent key) -- matching that shape here rather
    # than omitting the kwarg entirely.
    with pytest.raises(ValueError, match="PEXELS_API_KEY"):
        get_stock_media_provider(_settings(STOCK_MEDIA_PROVIDER_KWARGS={"pexels": {"api_key": ""}}))
