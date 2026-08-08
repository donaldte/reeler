"""Orchestrates the full render. Two modes, dispatched on
`settings_snapshot["export_mode"]`:

- `_render_highlight_reel` (default, "highlight_reel"): select clips ->
  extract+crop each -> concatenate (hard cut or true crossfade) ->
  build captions -> composite B-roll/watermark/mix music at final encode.
- `_render_full_video` ("full_video"): no clip selection/extraction at
  all — the entire source video, crop/scale + B-roll + captions +
  watermark + music composed in a single ffmpeg pass.

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
from domain.rendering.broll import BrollAssetLike, remap_broll_to_output_timeline
from domain.rendering.captions import TranscriptSegmentLike, build_ass_captions
from domain.rendering.clip_selection import HighlightLike, select_clips_for_duration
from domain.rendering.dimensions import compute_crop_params, get_output_dimensions
from domain.rendering.dto import BrollSpec, ClipSpec
from domain.rendering.ffmpeg_commands import (
    DEFAULT_XFADE_TRANSITION,
    XFADE_TRANSITION_MAP,
    build_concat_command,
    build_concat_list_content,
    build_crossfade_concat_command,
    build_extract_clip_command,
    build_final_encode_command,
    build_full_video_render_command,
)
from domain.rendering.music import build_music_generation_command

logger = logging.getLogger("reeler")

# Generous, not an expected duration — output is capped at 4 minutes by
# default (ExportSettings.output_duration_seconds), so highlight-reel
# renders should finish well under this; it exists as a safety net
# against a hung process.
FFMPEG_TIMEOUT_SECONDS = 1800

# export_mode="full_video" processes the entire source video in one pass
# instead of a handful of short highlight clips — on CPU-only hardware
# this can genuinely take a very long time for a long source video (see
# ffmpeg_commands.FULL_VIDEO_EXPORT_FORMAT_CODECS's docstring on the
# "-preset faster" tradeoff already made to help with this). A much
# longer timeout here is a disclosed consequence of that mode, not a bug.
FULL_VIDEO_FFMPEG_TIMEOUT_SECONDS = 6 * 3600

# How much of the stderr tail to keep in the raised error / stored on
# RenderJob.error_message — enough to see the actual ffmpeg complaint
# without dumping megabytes of unrelated encoder logging.
STDERR_TAIL_CHARS = 2000

ProgressCallback = Callable[[int, str], None]


def _run_ffmpeg(cmd: list[str], *, step: str, timeout: float = FFMPEG_TIMEOUT_SECONDS) -> None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
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


def _resolve_broll(
    broll_assets: Sequence[BrollAssetLike], clips: Sequence[ClipSpec], settings_snapshot: dict
) -> tuple[list[BrollSpec], list[Path]]:
    """Shared by both render modes: remaps broll_assets onto `clips`'
    output timeline and drops any that never downloaded an image (a
    best-effort BrollAsset row with `image_path is None` — see
    apps/highlights/tasks.py::_fetch_broll_assets). Returns parallel
    lists ready for ffmpeg_commands' broll_specs/broll_image_paths kwargs.
    """
    broll_type = settings_snapshot.get("broll_type", "none")
    if broll_type == "none" or not broll_assets:
        return [], []

    broll_specs: list[BrollSpec] = []
    broll_image_paths: list[Path] = []
    for asset, spec in remap_broll_to_output_timeline(broll_assets, clips):
        if not asset.image_path:
            continue
        broll_specs.append(spec)
        broll_image_paths.append(Path(asset.image_path))
    return broll_specs, broll_image_paths


def _resolve_watermark(settings_snapshot: dict) -> Path | None:
    logo_path = settings_snapshot.get("logo_image_path")
    return Path(logo_path) if logo_path else None


def render_video(
    *,
    source_path: Path,
    source_width: int,
    source_height: int,
    has_audio: bool,
    video_duration: float,
    transcript_segments: Sequence[TranscriptSegmentLike],
    highlights: Sequence[HighlightLike],
    broll_assets: Sequence[BrollAssetLike] = (),
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

    if settings_snapshot.get("export_mode", "highlight_reel") == "full_video":
        return _render_full_video(
            source_path=source_path,
            source_width=source_width,
            source_height=source_height,
            has_audio=has_audio,
            video_duration=video_duration,
            transcript_segments=transcript_segments,
            broll_assets=broll_assets,
            settings_snapshot=settings_snapshot,
            workdir=workdir,
            report=report,
        )
    return _render_highlight_reel(
        source_path=source_path,
        source_width=source_width,
        source_height=source_height,
        has_audio=has_audio,
        transcript_segments=transcript_segments,
        highlights=highlights,
        broll_assets=broll_assets,
        settings_snapshot=settings_snapshot,
        workdir=workdir,
        report=report,
    )


def _render_highlight_reel(
    *,
    source_path: Path,
    source_width: int,
    source_height: int,
    has_audio: bool,
    transcript_segments: Sequence[TranscriptSegmentLike],
    highlights: Sequence[HighlightLike],
    broll_assets: Sequence[BrollAssetLike],
    settings_snapshot: dict,
    workdir: Path,
    report: ProgressCallback,
) -> Path:
    report(10, "selecting_clips")
    clips = select_clips_for_duration(highlights, settings_snapshot["output_duration_seconds"])

    out_dims = get_output_dimensions(
        settings_snapshot["aspect_ratio"], settings_snapshot["video_quality"]
    )
    crop_params = compute_crop_params(source_width, source_height, out_dims.width, out_dims.height)

    report(20, "extracting_clips")
    clip_paths: list[Path] = []
    for index, clip in enumerate(clips):
        clip_output = workdir / f"clip_{index:03d}.mp4"
        cmd = build_extract_clip_command(
            source_path, clip, crop_params, out_dims, has_audio=has_audio, output_path=clip_output
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
    concatenated_path = workdir / "concatenated.mp4"
    # ExportSettings.transition_style is the master on/off switch ("none"
    # means hard cuts, full stop). A single surviving clip has nothing to
    # cross-fade with regardless of the setting (select_clips_for_duration
    # can legitimately return exactly one) -- falls back to a plain
    # concat either way.
    transition_style = settings_snapshot["transition_style"]
    if transition_style != "none" and len(clips) >= 2:
        _run_ffmpeg(
            build_crossfade_concat_command(
                clip_paths,
                [clip.duration for clip in clips],
                has_audio=has_audio,
                transition=XFADE_TRANSITION_MAP.get(transition_style, DEFAULT_XFADE_TRANSITION),
                output_path=concatenated_path,
            ),
            step="concatenating clips with crossfade",
        )
    else:
        concat_list_path = workdir / "concat_list.txt"
        concat_list_path.write_text(build_concat_list_content(clip_paths), encoding="utf-8")
        _run_ffmpeg(
            build_concat_command(concat_list_path, concatenated_path), step="concatenating clips"
        )

    music_path: Path | None = None
    # .get(..., "none"): older RenderJob rows created before music_style
    # was added to SNAPSHOT_FIELDS won't have the key in their frozen
    # snapshot, but those are never reprocessed (a RenderJob only renders
    # once) -- this default just keeps that theoretical case from raising.
    music_style = settings_snapshot.get("music_style", "none")
    if music_style != "none":
        report(75, "generating_music")
        music_path = workdir / "music.m4a"
        total_duration = sum(clip.duration for clip in clips)
        _run_ffmpeg(
            build_music_generation_command(music_style, total_duration, music_path),
            step="generating background music",
        )

    broll_specs, broll_image_paths = _resolve_broll(broll_assets, clips, settings_snapshot)
    watermark_path = _resolve_watermark(settings_snapshot)

    report(80, "encoding")
    export_format = settings_snapshot["export_format"]
    final_output_path = workdir / f"output.{export_format}"
    _run_ffmpeg(
        build_final_encode_command(
            concatenated_path,
            captions_path,
            music_path,
            export_format,
            broll_specs=broll_specs,
            broll_image_paths=broll_image_paths,
            broll_out_width=out_dims.width,
            broll_out_height=out_dims.height,
            watermark_path=watermark_path,
            has_audio=has_audio,
            output_path=final_output_path,
        ),
        step="final encode",
    )

    report(95, "finalizing")
    return final_output_path


def _render_full_video(
    *,
    source_path: Path,
    source_width: int,
    source_height: int,
    has_audio: bool,
    video_duration: float,
    transcript_segments: Sequence[TranscriptSegmentLike],
    broll_assets: Sequence[BrollAssetLike],
    settings_snapshot: dict,
    workdir: Path,
    report: ProgressCallback,
) -> Path:
    """No clip selection/extraction/concatenation — the entire source
    video is kept, in order. `output_duration_seconds`/`num_highlights`
    are simply unused in this mode.
    """
    report(10, "preparing")
    out_dims = get_output_dimensions(
        settings_snapshot["aspect_ratio"], settings_snapshot["video_quality"]
    )
    crop_params = compute_crop_params(source_width, source_height, out_dims.width, out_dims.height)

    # A single synthetic "clip" spanning the whole video -- lets
    # build_ass_captions and _resolve_broll be reused completely unchanged
    # (their cumulative-offset remapping degenerates to a 1:1 passthrough
    # against one clip covering [0, video_duration]).
    whole_video_clip = [ClipSpec(start=0.0, end=video_duration, rank=1)]

    report(30, "building_captions")
    captions_path: Path | None = None
    captions_wanted = (
        settings_snapshot["caption_style"] != "none"
        and settings_snapshot["subtitle_language"] != "none"
    )
    if captions_wanted:
        ass_content = build_ass_captions(
            transcript_segments,
            whole_video_clip,
            caption_style=settings_snapshot["caption_style"],
            font=settings_snapshot["font"],
            color_theme=settings_snapshot["color_theme"],
            output_width=out_dims.width,
            output_height=out_dims.height,
        )
        captions_path = workdir / "captions.ass"
        captions_path.write_text(ass_content, encoding="utf-8")

    music_path: Path | None = None
    music_style = settings_snapshot.get("music_style", "none")
    if music_style != "none":
        report(45, "generating_music")
        music_path = workdir / "music.m4a"
        _run_ffmpeg(
            build_music_generation_command(music_style, video_duration, music_path),
            step="generating background music",
        )

    broll_specs, broll_image_paths = _resolve_broll(
        broll_assets, whole_video_clip, settings_snapshot
    )
    watermark_path = _resolve_watermark(settings_snapshot)

    report(60, "encoding")
    export_format = settings_snapshot["export_format"]
    final_output_path = workdir / f"output.{export_format}"
    _run_ffmpeg(
        build_full_video_render_command(
            source_path,
            crop_params,
            out_dims,
            captions_path,
            music_path,
            export_format,
            broll_specs=broll_specs,
            broll_image_paths=broll_image_paths,
            watermark_path=watermark_path,
            has_audio=has_audio,
            output_path=final_output_path,
        ),
        step="encoding full video",
        timeout=FULL_VIDEO_FFMPEG_TIMEOUT_SECONDS,
    )

    report(95, "finalizing")
    return final_output_path
