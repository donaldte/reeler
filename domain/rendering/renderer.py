"""Orchestrates the full render: select clips -> extract+crop each ->
build captions -> concatenate -> burn captions + final encode.

The one module in domain/rendering with side effects (subprocess calls) —
same fixed-argv/no-shell pattern as domain/media/ffprobe.py::probe.
ffmpeg failures are always raised as PermanentPipelineError with the
captured stderr — they're essentially always deterministic (bad params,
unsupported codec, corrupt input), never worth retrying as-is.
"""

import logging
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from domain.exceptions import PermanentPipelineError
from domain.rendering.captions import TranscriptSegmentLike, build_ass_captions
from domain.rendering.clip_selection import HighlightLike, select_clips_for_duration
from domain.rendering.dimensions import compute_crop_params, get_output_dimensions
from domain.rendering.ffmpeg_commands import (
    build_concat_command,
    build_concat_list_content,
    build_extract_clip_command,
    build_final_encode_command,
)

logger = logging.getLogger("reeler")

# Generous, not an expected duration — output is capped at 4 minutes
# (ExportSettings.output_duration_seconds max), so real renders should
# finish well under this; it exists as a safety net against a hung process.
FFMPEG_TIMEOUT_SECONDS = 1800

# How much of the stderr tail to keep in the raised error / stored on
# RenderJob.error_message — enough to see the actual ffmpeg complaint
# without dumping megabytes of unrelated encoder logging.
STDERR_TAIL_CHARS = 2000

ProgressCallback = Callable[[int, str], None]


def _run_ffmpeg(cmd: list[str], *, step: str) -> None:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS, check=False
        )
    except FileNotFoundError as exc:
        raise PermanentPipelineError(
            "ffmpeg executable not found. Is ffmpeg installed in this environment?"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PermanentPipelineError(f"ffmpeg timed out during {step}") from exc

    if result.returncode != 0:
        stderr_tail = (
            result.stderr[-STDERR_TAIL_CHARS:] if result.stderr else "(no stderr captured)"
        )
        logger.warning(
            "ffmpeg failed during %s (exit %d): %s", step, result.returncode, stderr_tail
        )
        raise PermanentPipelineError(f"ffmpeg failed during {step}: {stderr_tail}")


def render_video(
    *,
    source_path: Path,
    source_width: int,
    source_height: int,
    has_audio: bool,
    transcript_segments: Sequence[TranscriptSegmentLike],
    highlights: Sequence[HighlightLike],
    settings_snapshot: dict,
    workdir: Path,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    """Runs the full pipeline in `workdir` (caller owns its lifecycle —
    typically a `tempfile.TemporaryDirectory`) and returns the path to the
    final output file, itself inside `workdir`. The caller must copy it
    out (e.g. into a Django FileField) before the directory is cleaned up.

    `settings_snapshot` is the plain dict shape of
    `RenderJob.settings_snapshot` — see apps/renders/models.py.
    """

    def report(pct: int, stage: str) -> None:
        if progress_callback is not None:
            progress_callback(pct, stage)

    report(10, "selecting_clips")
    clips = select_clips_for_duration(highlights, settings_snapshot["output_duration_seconds"])

    out_dims = get_output_dimensions(
        settings_snapshot["aspect_ratio"], settings_snapshot["video_quality"]
    )
    crop_params = compute_crop_params(source_width, source_height, out_dims.width, out_dims.height)
    apply_fade = settings_snapshot["transition_style"] != "none"

    report(20, "extracting_clips")
    clip_paths: list[Path] = []
    for index, clip in enumerate(clips):
        clip_output = workdir / f"clip_{index:03d}.mp4"
        cmd = build_extract_clip_command(
            source_path,
            clip,
            crop_params,
            out_dims,
            has_audio=has_audio,
            apply_fade=apply_fade,
            output_path=clip_output,
        )
        _run_ffmpeg(cmd, step=f"extracting clip {index + 1}/{len(clips)}")
        clip_paths.append(clip_output)

    report(55, "building_captions")
    captions_path: Path | None = None
    captions_wanted = (
        settings_snapshot["caption_style"] != "none"
        and settings_snapshot["subtitle_language"] != "none"
    )
    if captions_wanted:
        ass_content = build_ass_captions(
            transcript_segments,
            clips,
            caption_style=settings_snapshot["caption_style"],
            font=settings_snapshot["font"],
            color_theme=settings_snapshot["color_theme"],
            output_width=out_dims.width,
            output_height=out_dims.height,
        )
        captions_path = workdir / "captions.ass"
        captions_path.write_text(ass_content, encoding="utf-8")

    report(65, "concatenating")
    concat_list_path = workdir / "concat_list.txt"
    concat_list_path.write_text(build_concat_list_content(clip_paths), encoding="utf-8")
    concatenated_path = workdir / "concatenated.mp4"
    _run_ffmpeg(
        build_concat_command(concat_list_path, concatenated_path), step="concatenating clips"
    )

    report(80, "encoding")
    export_format = settings_snapshot["export_format"]
    final_output_path = workdir / f"output.{export_format}"
    _run_ffmpeg(
        build_final_encode_command(
            concatenated_path,
            captions_path,
            export_format,
            has_audio=has_audio,
            output_path=final_output_path,
        ),
        step="final encode",
    )

    report(95, "finalizing")
    return final_output_path
