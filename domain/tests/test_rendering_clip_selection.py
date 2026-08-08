from dataclasses import dataclass

import pytest

from domain.rendering.clip_selection import select_clips_for_duration


@dataclass
class _Highlight:
    rank: int
    start_time: float
    end_time: float


def test_selects_all_highlights_when_they_fit():
    highlights = [
        _Highlight(rank=1, start_time=10.0, end_time=20.0),  # 10s
        _Highlight(rank=2, start_time=30.0, end_time=40.0),  # 10s
    ]
    clips = select_clips_for_duration(highlights, target_duration=60.0)

    assert len(clips) == 2
    assert [c.start for c in clips] == [10.0, 30.0]


def test_stops_including_once_target_duration_would_be_exceeded():
    highlights = [
        _Highlight(rank=1, start_time=0.0, end_time=20.0),  # 20s, rank 1 -> always included
        _Highlight(rank=2, start_time=50.0, end_time=70.0),  # 20s, fits (total 40s)
        _Highlight(rank=3, start_time=100.0, end_time=130.0),  # 30s, would push to 70s > 45s target
    ]
    clips = select_clips_for_duration(highlights, target_duration=45.0)

    assert len(clips) == 2
    assert {c.rank for c in clips} == {1, 2}


def test_always_includes_at_least_the_top_ranked_highlight_even_if_it_overshoots():
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=300.0)]  # 300s, way over any target
    clips = select_clips_for_duration(highlights, target_duration=60.0)

    assert len(clips) == 1
    assert clips[0].duration == 300.0


def test_included_clips_are_sorted_chronologically_not_by_rank():
    highlights = [
        _Highlight(rank=1, start_time=100.0, end_time=110.0),  # most compelling, but happens later
        _Highlight(rank=2, start_time=0.0, end_time=10.0),  # less compelling, happens first
    ]
    clips = select_clips_for_duration(highlights, target_duration=60.0)

    assert [c.start for c in clips] == [0.0, 100.0]


def test_raises_on_empty_highlights():
    with pytest.raises(ValueError, match="at least one highlight"):
        select_clips_for_duration([], target_duration=60.0)


def test_clip_duration_property():
    highlights = [_Highlight(rank=1, start_time=5.0, end_time=12.5)]
    clips = select_clips_for_duration(highlights, target_duration=60.0)
    assert clips[0].duration == 7.5
