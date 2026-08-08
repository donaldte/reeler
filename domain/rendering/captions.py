"""Builds a `.ass` subtitle file from transcript segments, remapped onto
the final concatenated-clip timeline and styled per ExportSettings.

Known limitations (see docs/ai_pipeline.md and docs/roadmap.md):
- `caption_style="karaoke"` renders identically to `"bold"` — true
  word-by-word karaoke needs word-level timestamps, which
  `FasterWhisperProvider` doesn't currently request
  (`word_timestamps=False`).
- Fonts are requested by family name only; if a requested font isn't
  installed in the container, libass silently substitutes a default —
  no error, just a visual fallback.
- `subtitle_language` values other than `"auto"`/the transcript's own
  detected language still render the original-language transcript — no
  translation capability exists yet.
"""

from collections.abc import Sequence
from typing import Protocol

from domain.rendering.dto import ClipSpec


class TranscriptSegmentLike(Protocol):
    start_time: float
    end_time: float
    text: str


FONT_NAME_MAP = {
    "inter": "Inter",
    "montserrat": "Montserrat",
    "anton": "Anton",
    "roboto": "Roboto",
}
DEFAULT_FONT_NAME = "Arial"

# BorderStyle 1 = outline+shadow, no box. BorderStyle 3 = opaque box behind text.
CAPTION_STYLE_PARAMS = {
    "minimal": {"fontsize": 36, "bold": False, "border_style": 1, "outline_width": 1},
    "bold": {"fontsize": 56, "bold": True, "border_style": 3, "outline_width": 2},
    "karaoke": {"fontsize": 56, "bold": True, "border_style": 3, "outline_width": 2},
}
DEFAULT_CAPTION_STYLE = "bold"

# ASS colors are &HAABBGGRR (alpha 00=opaque..FF=transparent, then B,G,R).
COLOR_THEME_PARAMS = {
    "default": {"primary": "&H00FFFFFF", "outline": "&H00000000", "back": "&H80000000"},
    "vibrant": {"primary": "&H0000FFFF", "outline": "&H00000000", "back": "&H80000000"},
    "dark": {"primary": "&H00FFFFFF", "outline": "&H00000000", "back": "&HC0000000"},
    "pastel": {"primary": "&H00E6FFC8", "outline": "&H00000000", "back": "&H80000000"},
    "monochrome": {"primary": "&H00FFFFFF", "outline": "&H00000000", "back": "&H80000000"},
}
DEFAULT_COLOR_THEME = "default"


def _format_ass_timestamp(total_seconds: float) -> str:
    """ASS timestamps are `H:MM:SS.cc` — centiseconds, not milliseconds."""
    total_centiseconds = round(total_seconds * 100)
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def build_ass_captions(
    segments: Sequence[TranscriptSegmentLike],
    clips: Sequence[ClipSpec],
    *,
    caption_style: str,
    font: str,
    color_theme: str,
    output_width: int,
    output_height: int,
) -> str:
    """Renders a complete `.ass` document. Caller is responsible for
    skipping this entirely when captions are disabled
    (`caption_style == "none"` or `subtitle_language == "none"`).
    """
    style = CAPTION_STYLE_PARAMS.get(caption_style, CAPTION_STYLE_PARAMS[DEFAULT_CAPTION_STYLE])
    colors = COLOR_THEME_PARAMS.get(color_theme, COLOR_THEME_PARAMS[DEFAULT_COLOR_THEME])
    font_name = FONT_NAME_MAP.get(font, DEFAULT_FONT_NAME)

    dialogue_lines: list[str] = []
    cumulative_offset = 0.0
    for clip in clips:
        overlapping = [
            seg for seg in segments if seg.end_time > clip.start and seg.start_time < clip.end
        ]
        for seg in overlapping:
            new_start = cumulative_offset + max(0.0, seg.start_time - clip.start)
            new_end = cumulative_offset + min(clip.duration, seg.end_time - clip.start)
            if new_end <= new_start:
                continue
            text = seg.text.strip().replace("\n", "\\N").replace("{", "(").replace("}", ")")
            dialogue_lines.append(
                f"Dialogue: 0,{_format_ass_timestamp(new_start)},"
                f"{_format_ass_timestamp(new_end)},Default,,0,0,0,,{text}"
            )
        cumulative_offset += clip.duration

    margin_v = round(output_height * 0.08)
    bold_flag = -1 if style["bold"] else 0

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {output_width}\n"
        f"PlayResY: {output_height}\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{style['fontsize']},{colors['primary']},&H000000FF,"
        f"{colors['outline']},{colors['back']},{bold_flag},0,0,0,100,100,0,0,"
        f"{style['border_style']},{style['outline_width']},1,2,10,10,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    return header + "\n".join(dialogue_lines) + "\n"
