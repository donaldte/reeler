"""Pluggable stock-media-search capability — mirrors domain.ai.base's
LLMProvider/registry pattern exactly (ABC + registry + provider
implementations), just for a different capability. See
domain/stock_media/registry.py and docs/ai_pipeline.md.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class StockMediaResultDTO:
    id: str
    image_url: str
    width: int
    height: int
    photographer: str
    source_page_url: str


class StockMediaProvider(ABC):
    """Interface every stock-media search backend must implement.
    Implementations live in `domain/stock_media/providers/` and are
    registered in `domain/stock_media/registry.py`'s STOCK_MEDIA_PROVIDERS
    mapping.
    """

    name: ClassVar[str]

    @abstractmethod
    def search_media(
        self, *, query: str, orientation: str = "portrait", per_page: int = 5
    ) -> list[StockMediaResultDTO]:
        raise NotImplementedError
