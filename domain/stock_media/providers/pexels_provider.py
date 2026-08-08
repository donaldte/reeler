"""Stock photo search against the Pexels API — the default (and, for this
pass, only) StockMediaProvider. Free API key: https://www.pexels.com/api/.
Selected via STOCK_MEDIA_PROVIDER=pexels (the default).
"""

from typing import ClassVar

import httpx

from domain.ai.providers.http_utils import classify_http_status_error
from domain.exceptions import ProviderResponseParseError, TransientProviderError
from domain.stock_media.base import StockMediaProvider, StockMediaResultDTO

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# Pexels' `src` dict offers several pre-sized renditions; large2x (up to
# ~1880px on the long edge) is a deliberate middle ground -- enough
# resolution for domain.rendering.broll's Ken Burns pre-scale/zoom to have
# real detail to zoom into, without downloading `original` (often several
# MB, unnecessary for a still that only fills part of a short vertical
# video for a few seconds).
PEXELS_IMAGE_SIZE_KEY = "large2x"


class PexelsProvider(StockMediaProvider):
    name: ClassVar[str] = "pexels"

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("PEXELS_API_KEY is required when STOCK_MEDIA_PROVIDER=pexels")
        self.api_key = api_key
        self.timeout = timeout

    def search_media(
        self, *, query: str, orientation: str = "portrait", per_page: int = 5
    ) -> list[StockMediaResultDTO]:
        try:
            response = httpx.get(
                PEXELS_SEARCH_URL,
                headers={"Authorization": self.api_key},
                params={"query": query, "orientation": orientation, "per_page": per_page},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TransientProviderError(f"Pexels request timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            hint = "Check PEXELS_API_KEY." if exc.response.status_code in (401, 403) else ""
            raise classify_http_status_error(exc, provider_name="Pexels", hint=hint) from exc
        except httpx.HTTPError as exc:
            raise TransientProviderError(f"Pexels request failed: {exc}") from exc

        try:
            photos = response.json()["photos"]
            return [
                StockMediaResultDTO(
                    id=str(photo["id"]),
                    image_url=photo["src"][PEXELS_IMAGE_SIZE_KEY],
                    width=photo["width"],
                    height=photo["height"],
                    photographer=photo["photographer"],
                    source_page_url=photo["url"],
                )
                for photo in photos
            ]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ProviderResponseParseError(f"Unexpected Pexels response shape: {exc}") from exc
