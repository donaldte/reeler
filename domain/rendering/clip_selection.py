"""Picks which highlights make it into the final render, and in what order.

Chronological order, greedily fit to a target duration — not the LLM's
"most compelling first" rank order — so the exported short reads as a
coherent narrative rather than jumping around the source video.
"""

from collections.abc import Sequence
from typing import Protocol

from domain.rendering.dto import ClipSpec


class HighlightLike(Protocol):
    """Structural type so this module doesn't need to import the Django
    `Highlight` model (domain/ stays framework-free) — any object with
    these three attributes works, including the ORM model itself.
    """

    rank: int
    start_time: float
    end_time: float


def select_clips_for_duration(
    highlights: Sequence[HighlightLike], target_duration: float
) -> list[ClipSpec]:
    """Greedily includes highlights in rank order (most compelling first)
    while the running total still fits `target_duration`, then re-sorts
    the *included* set chronologically by original start time.

    Always includes at least one clip, even if the top-ranked highlight
    alone exceeds `target_duration` — overshooting slightly is better than
    an empty render. Raises ValueError if `highlights` is empty.
    """
    if not highlights:
        raise ValueError("select_clips_for_duration requires at least one highlight")

    by_rank = sorted(highlights, key=lambda h: h.rank)
    selected: list[HighlightLike] = []
    total = 0.0
    for highlight in by_rank:
        duration = highlight.end_time - highlight.start_time
        if selected and total + duration > target_duration:
            break
        selected.append(highlight)
        total += duration

    selected.sort(key=lambda h: h.start_time)
    return [ClipSpec(start=h.start_time, end=h.end_time, rank=h.rank) for h in selected]
