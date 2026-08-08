from dataclasses import dataclass

from domain.rendering.captions import build_ass_captions
from domain.rendering.dto import ClipSpec


@dataclass
class _Segment:
    start_time: float
    end_time: float
    text: str


def test_header_includes_resolution_and_style():
    ass = build_ass_captions(
        [], [], caption_style="bold", font="inter", color_theme="default",
        output_width=1080, output_height=1920,
    )  # fmt: skip
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "Fontname" in ass  # format header present
    assert "Inter" in ass  # mapped font family name


def test_falls_back_to_default_font_for_unknown_value():
    ass = build_ass_captions(
        [], [], caption_style="bold", font="comic-sans", color_theme="default",
        output_width=1080, output_height=1920,
    )  # fmt: skip
    assert "Style: Default,Arial," in ass


def test_karaoke_style_matches_bold_style():
    common_kwargs = {
        "segments": [], "clips": [], "font": "inter", "color_theme": "default",
        "output_width": 1080, "output_height": 1920,
    }  # fmt: skip
    bold_ass = build_ass_captions(caption_style="bold", **common_kwargs)
    karaoke_ass = build_ass_captions(caption_style="karaoke", **common_kwargs)
    # Same style line (only the header/style differs by caption_style; both
    # produce identical Style directives since karaoke is a documented
    # fallback to bold, not a distinct implementation yet).
    bold_style_line = next(line for line in bold_ass.splitlines() if line.startswith("Style:"))
    karaoke_style_line = next(
        line for line in karaoke_ass.splitlines() if line.startswith("Style:")
    )
    assert bold_style_line == karaoke_style_line


def test_single_clip_timestamps_remapped_relative_to_clip_start():
    segments = [_Segment(start_time=12.0, end_time=14.0, text="hello")]
    clips = [ClipSpec(start=10.0, end=20.0, rank=1)]

    ass = build_ass_captions(
        segments, clips, caption_style="bold", font="inter", color_theme="default",
        output_width=1080, output_height=1920,
    )  # fmt: skip

    # segment starts 2s into the clip (12 - 10), clip starts at timeline 0
    assert "Dialogue: 0,0:00:02.00,0:00:04.00,Default,,0,0,0,,hello" in ass


def test_second_clip_timestamps_offset_by_first_clips_duration():
    segments = [
        _Segment(start_time=1.0, end_time=3.0, text="first"),
        _Segment(start_time=51.0, end_time=53.0, text="second"),
    ]
    clips = [
        ClipSpec(start=0.0, end=10.0, rank=1),  # 10s clip -> timeline [0, 10)
        ClipSpec(start=50.0, end=60.0, rank=2),  # next clip starts at timeline offset 10
    ]

    ass = build_ass_captions(
        segments, clips, caption_style="bold", font="inter", color_theme="default",
        output_width=1080, output_height=1920,
    )  # fmt: skip

    assert "0:00:01.00,0:00:03.00,Default,,0,0,0,,first" in ass
    # second segment: 51-50=1s into its clip, offset by 10s from clip 1 -> starts at 11s
    assert "0:00:11.00,0:00:13.00,Default,,0,0,0,,second" in ass


def test_segment_clipped_to_clip_boundaries():
    # Segment starts before the clip and ends after it -- must be clipped,
    # not dropped or extended past the clip's own duration.
    segments = [_Segment(start_time=-5.0, end_time=25.0, text="overlapping")]
    clips = [ClipSpec(start=0.0, end=10.0, rank=1)]

    ass = build_ass_captions(
        segments, clips, caption_style="bold", font="inter", color_theme="default",
        output_width=1080, output_height=1920,
    )  # fmt: skip

    assert "Dialogue: 0,0:00:00.00,0:00:10.00,Default,,0,0,0,,overlapping" in ass


def test_segment_outside_any_clip_is_excluded():
    segments = [_Segment(start_time=100.0, end_time=105.0, text="never shown")]
    clips = [ClipSpec(start=0.0, end=10.0, rank=1)]

    ass = build_ass_captions(
        segments, clips, caption_style="bold", font="inter", color_theme="default",
        output_width=1080, output_height=1920,
    )  # fmt: skip

    assert "never shown" not in ass


def test_zero_duration_segment_after_clipping_is_skipped():
    """A degenerate zero-length segment (e.g. start_time == end_time) must
    not produce a Dialogue line with new_end <= new_start.
    """
    segments = [_Segment(start_time=5.0, end_time=5.0, text="instant")]
    clips = [ClipSpec(start=0.0, end=10.0, rank=1)]

    ass = build_ass_captions(
        segments, clips, caption_style="bold", font="inter", color_theme="default",
        output_width=1080, output_height=1920,
    )  # fmt: skip

    assert "instant" not in ass


def test_curly_braces_in_text_are_escaped():
    """ASS uses {...} for inline override tags -- text containing literal
    braces must not be interpreted as styling directives.
    """
    segments = [_Segment(start_time=0.0, end_time=2.0, text="say {hello}")]
    clips = [ClipSpec(start=0.0, end=10.0, rank=1)]

    ass = build_ass_captions(
        segments, clips, caption_style="bold", font="inter", color_theme="default",
        output_width=1080, output_height=1920,
    )  # fmt: skip

    assert "{hello}" not in ass
    assert "(hello)" in ass
