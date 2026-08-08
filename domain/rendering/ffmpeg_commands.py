"""Pure ffmpeg argv builders — no subprocess calls here (see
domain/rendering/renderer.py for execution). Every function returns a
plain `list[str]` so it's fully unit-testable without ffmpeg installed.
"""

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from domain.rendering.broll import (
    BROLL_FPS,
    BROLL_OUTPUT_VIDEO_LABEL,
    build_broll_filter_complex,
)
from domain.rendering.dto import BrollSpec, ClipSpec, CropParams, OutputDimensions

# Fixed pre-attenuation applied to the generated music track before mixing
# it under dialogue — a static mix, not true ducking (no sidechain
# analysis of speech level), but enough to keep music from competing with
# dialogue. See build_final_encode_command's `amix` usage below for why
# this alone isn't sufficient without also disabling amix's normalize.
MUSIC_MIX_VOLUME = 0.25

# Opacity applied to the watermark (multiplies whatever alpha the source
# PNG already has, so a semi-transparent logo gets *more* transparent,
# not clobbered). Margin is in output pixels, not a % of frame size — a
# fixed on-screen size regardless of aspect ratio/resolution.
WATERMARK_OPACITY = 0.8
WATERMARK_MARGIN_PX = 24

# The watermark is scaled to this fraction of the output frame's width
# before compositing (aspect ratio preserved) -- without this, a
# normal-resolution uploaded logo would composite at its own native
# resolution and could cover the entire frame. ~18% reads as a small
# corner logo across the aspect ratios this project supports (9:16, 1:1,
# 16:9), not something that competes with the video itself.
WATERMARK_WIDTH_FRACTION = 0.18

# overlay= x/y expressions per corner, in terms of overlay's own w/h (the
# watermark's dimensions *after* the scale above) and the base video's
# main_w/main_h — the standard overlay-filter idiom for anchoring to an
# edge with a fixed pixel margin regardless of watermark image size.
WATERMARK_POSITION_EXPRESSIONS: dict[str, tuple[str, str]] = {
    "top_left": (f"{WATERMARK_MARGIN_PX}", f"{WATERMARK_MARGIN_PX}"),
    "top_right": (f"main_w-w-{WATERMARK_MARGIN_PX}", f"{WATERMARK_MARGIN_PX}"),
    "bottom_left": (f"{WATERMARK_MARGIN_PX}", f"main_h-h-{WATERMARK_MARGIN_PX}"),
    "bottom_right": (f"main_w-w-{WATERMARK_MARGIN_PX}", f"main_h-h-{WATERMARK_MARGIN_PX}"),
}
# Bottom corner by default -- a logo overlaying the top of a 9:16 short
# tends to collide with a platform's own UI chrome (username/caption
# overlays there); bottom-right is the conventional short-form placement.
DEFAULT_WATERMARK_POSITION = "bottom_right"

# Crossfade duration for true xfade/acrossfade transitions between
# concatenated clips (see build_crossfade_concat_command). Replaces the
# old per-clip FADE_DURATION_SECONDS fade-to-black entirely — a real
# crossfade and a per-clip fade-to-black are mutually exclusive, not
# layered (a fade underneath a crossfade would visibly dip at the seam).
CROSSFADE_DURATION_SECONDS = 0.5

# ExportSettings.TransitionStyle values ("fade"/"slide"/"zoom") mapped to
# xfade's own `transition=` names. "zoom" -> "fade", not the more literal
# "zoomin": xfade's base transition set (fade/wipe*/slide*/circlecrop/...)
# shipped with the filter in ffmpeg 4.3; "zoomin" and similar landed in
# later releases, a real version-compatibility risk on an older-but-still-
# 4.3+ ffmpeg build that hasn't been confirmed on real hardware — safe
# default now, upgradeable once confirmed. See docs/roadmap.md.
XFADE_TRANSITION_MAP: dict[str, str] = {"fade": "fade", "slide": "slideleft", "zoom": "fade"}
DEFAULT_XFADE_TRANSITION = "fade"

# mp4/mov: broadly compatible H.264 + AAC. webm: VP9 + Opus (H.264 isn't a
# valid webm codec). CRF-based rather than explicit bitrates — output
# resolution already differentiates the video_quality tiers, so a
# consistent CRF keeps encoded quality comparable across them without
# guessing per-resolution bitrate targets.
EXPORT_FORMAT_CODECS: dict[str, dict[str, list[str]]] = {
    "mp4": {
        "video": ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p"],
        "audio": ["-c:a", "aac", "-b:a", "192k"],
    },
    "mov": {
        "video": ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p"],
        "audio": ["-c:a", "aac", "-b:a", "192k"],
    },
    "webm": {
        "video": ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"],
        "audio": ["-c:a", "libopus", "-b:a", "128k"],
    },
}
DEFAULT_EXPORT_FORMAT = "mp4"

# Same shape as EXPORT_FORMAT_CODECS but "faster" instead of "medium" for
# libx264 — used only by build_full_video_render_command. A single encode
# pass over a long (10-30+ min) source video at "medium" could take a
# very long time on CPU-only hardware; "faster" is a disclosed,
# reasonable speed/quality tradeoff given the much larger amount of
# footage full-video mode processes, not a silent quality cut. webm is
# left unchanged (libvpx-vp9 has no directly equivalent "preset" knob in
# the codec dict shape used here).
FULL_VIDEO_EXPORT_FORMAT_CODECS: dict[str, dict[str, list[str]]] = {
    "mp4": {
        "video": ["-c:v", "libx264", "-preset", "faster", "-crf", "23", "-pix_fmt", "yuv420p"],
        "audio": ["-c:a", "aac", "-b:a", "192k"],
    },
    "mov": {
        "video": ["-c:v", "libx264", "-preset", "faster", "-crf", "23", "-pix_fmt", "yuv420p"],
        "audio": ["-c:a", "aac", "-b:a", "192k"],
    },
    "webm": EXPORT_FORMAT_CODECS["webm"],
}


def build_extract_clip_command(
    source_path: Path,
    clip: ClipSpec,
    crop_params: CropParams,
    out_dims: OutputDimensions,
    *,
    has_audio: bool,
    output_path: Path,
) -> list[str]:
    """Extracts one highlight from the source video, cropped/scaled to the
    target aspect ratio and resolution. Always re-encodes (crop/scale
    can't be done with stream copy) using the same codec/settings for
    every clip, which is what makes both the hard-cut concat-demuxer step
    (`-c copy`) and the true-crossfade `xfade` step (which requires
    identical resolution/framerate/pixel format across inputs) safe.

    No per-clip fade here (unlike earlier versions of this function) —
    transitions are now handled once, at the seam between clips, by
    either build_concat_command (hard cuts) or
    build_crossfade_concat_command (true crossfade), never inside a
    single clip's own extraction.

    `-ss`/`-to` both given as *input* options (before `-i`) — the
    unambiguous, standard "extract from absolute position A to absolute
    position B in the source" idiom; mixing an input `-ss` with an output
    `-to` has different (seek-relative) semantics and is deliberately
    avoided here.
    """
    filters = [
        f"crop={crop_params.width}:{crop_params.height}:{crop_params.x}:{crop_params.y}",
        f"scale={out_dims.width}:{out_dims.height}",
    ]

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{clip.start:.3f}",
        "-to", f"{clip.end:.3f}",
        "-i", str(source_path),
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
    ]  # fmt: skip
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += [str(output_path)]
    return cmd


def build_concat_list_content(clip_paths: list[Path]) -> str:
    """Content for the concat demuxer's list file. Single quotes in a path
    are escaped per the documented concat-demuxer convention
    (`'` -> `'\\''`) — defensive, since our own tempfile paths never
    contain one in practice.
    """
    lines = [f"file '{str(p).replace("'", "'\\''")}'" for p in clip_paths]
    return "\n".join(lines) + "\n"


def build_concat_command(concat_list_path: Path, output_path: Path) -> list[str]:
    """Concatenates pre-extracted clips with `-c copy` — safe only because
    every clip was forced through identical crop/scale/codec settings by
    build_extract_clip_command, so no re-encode is needed here.
    """
    return [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list_path),
        "-c", "copy",
        str(output_path),
    ]  # fmt: skip


def build_crossfade_concat_command(
    clip_paths: list[Path],
    clip_durations: list[float],
    *,
    has_audio: bool,
    crossfade_duration: float = CROSSFADE_DURATION_SECONDS,
    transition: str = DEFAULT_XFADE_TRANSITION,
    output_path: Path,
) -> list[str]:
    """Concatenates >= 2 pre-extracted clips with true `xfade` (video) /
    `acrossfade` (audio, only if has_audio) crossfades at each seam,
    instead of the concat demuxer's hard-cut `-c copy`. Unlike
    build_concat_command, this always re-encodes — xfade/acrossfade need
    decoded frames/samples to blend, so stream copy is never possible
    here; that's the real cost of true crossfades vs. the old per-clip
    fade-to-black + concat-demuxer approach.

    Requires >= 2 clips (nothing to cross-fade with just one — caller
    must fall back to build_concat_command for a single-clip render,
    which select_clips_for_duration can legitimately produce).

    xfade requires identical resolution/framerate/pixel format across all
    inputs — guaranteed here because every clip already went through
    build_extract_clip_command's identical crop/scale/codec settings
    (same as what makes -c copy concat safe today). Framerate
    specifically is only *implicitly* consistent (every clip is extracted
    from the same single source_path, so they inherit one native
    framerate) — not something build_extract_clip_command pins explicitly
    with `-r`; if clips from multiple differently-framed source videos
    were ever concatenated in one render, this assumption would break.

    Raises:
        ValueError: fewer than 2 clips, or len(clip_paths) !=
            len(clip_durations).
    """
    if len(clip_paths) != len(clip_durations):
        raise ValueError("clip_paths and clip_durations must be the same length")
    if len(clip_paths) < 2:
        raise ValueError("build_crossfade_concat_command requires at least 2 clips")

    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]

    video_parts: list[str] = []
    audio_parts: list[str] = []
    prev_v, prev_a = "0:v", "0:a"
    last_index = len(clip_paths) - 1

    # xfade's `offset` is where the crossfade starts on the FIRST input's
    # OWN timeline — for link k (k=1..N-1, joining clip k+1 into the
    # chain), that first input is the *previous link's output* once k > 1,
    # not the original clip. `cumulative` tracks that output's running
    # duration: each crossfade shrinks the combined duration by the
    # overlapped region, so offset_k = cumulative_before_this_seam -
    # crossfade_duration (the documented common mistake is computing this
    # against the raw, un-shrunk sum of durations instead).
    cumulative = clip_durations[0]
    for i in range(1, len(clip_paths)):
        offset = cumulative - crossfade_duration
        v_out = "vout" if i == last_index else f"v{i}"
        a_out = "aout" if i == last_index else f"a{i}"

        video_parts.append(
            f"[{prev_v}][{i}:v]xfade=transition={transition}:"
            f"duration={crossfade_duration:.3f}:offset={offset:.3f}[{v_out}]"
        )
        if has_audio:
            audio_parts.append(
                f"[{prev_a}][{i}:a]acrossfade=duration={crossfade_duration:.3f}[{a_out}]"
            )
        prev_v, prev_a = v_out, a_out
        cumulative += clip_durations[i] - crossfade_duration

    cmd += ["-filter_complex", ";".join(video_parts + audio_parts)]
    cmd += ["-map", "[vout]"]
    cmd += ["-map", "[aout]"] if has_audio else ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p"]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += [str(output_path)]
    return cmd


def build_watermark_filter_complex(
    base_video_label: str,
    watermark_input_index: int,
    position: str,
    out_width: int,
    *,
    output_label: str = "vwatermark",
) -> str:
    """Returns a filter_complex fragment compositing a small,
    semi-transparent logo (already added as ffmpeg input
    `watermark_input_index`, e.g. `-i logo.png`) onto `base_video_label`
    for the *entire* render — no `enable=` gate, unlike broll's windowed
    overlay, since the watermark should be visible start to finish.

    `scale={target_w}:-2` is load-bearing, not cosmetic: without it, the
    watermark composites at whatever resolution the uploaded image
    actually is, which for any normal photo/logo upload means it covers
    a large fraction (often all) of the frame instead of sitting as a
    small corner mark. `-2` (not `-1`) keeps the scaled height even, as
    required by libx264's default 4:2:0 chroma subsampling.

    `format=rgba,colorchannelmixer=aa={WATERMARK_OPACITY}` is what
    actually reduces opacity — overlay itself has no opacity option;
    colorchannelmixer's `aa` multiplies the existing alpha channel, so a
    PNG with its own partial transparency gets scaled down further rather
    than replaced outright.
    """
    target_w = max(2, round(out_width * WATERMARK_WIDTH_FRACTION))
    x_expr, y_expr = WATERMARK_POSITION_EXPRESSIONS.get(
        position, WATERMARK_POSITION_EXPRESSIONS[DEFAULT_WATERMARK_POSITION]
    )
    return (
        f"[{watermark_input_index}:v]scale={target_w}:-2,format=rgba,"
        f"colorchannelmixer=aa={WATERMARK_OPACITY}[wm];"
        f"[{base_video_label}][wm]overlay=x={x_expr}:y={y_expr}[{output_label}]"
    )


def _escape_ass_filter_path(path: Path) -> str:
    # libass filter argument escaping: backslashes and colons are special
    # inside ffmpeg filter option strings.
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _append_broll_inputs(
    cmd: list[str],
    broll_specs: Sequence[BrollSpec],
    broll_image_paths: Sequence[Path],
    next_index: int,
) -> tuple[list[BrollSpec], int]:
    """Appends `-loop 1 -framerate BROLL_FPS -i <path>` for each B-roll
    image (in the same order as broll_specs) and returns the specs
    re-keyed to their *actual* assigned input indices, plus the next free
    index — re-deriving indices here (rather than trusting whatever
    `image_input_index` the caller's specs already carry) keeps this
    function self-contained and correct regardless of how many other
    inputs (music, watermark) precede or follow the B-roll images.
    """
    if len(broll_specs) != len(broll_image_paths):
        raise ValueError("broll_specs and broll_image_paths must be the same length")
    resolved: list[BrollSpec] = []
    for spec, path in zip(broll_specs, broll_image_paths, strict=True):
        cmd += ["-loop", "1", "-framerate", str(BROLL_FPS), "-i", str(path)]
        resolved.append(replace(spec, image_input_index=next_index))
        next_index += 1
    return resolved, next_index


def build_final_encode_command(
    input_path: Path,
    captions_path: Path | None,
    music_path: Path | None,
    export_format: str,
    *,
    broll_specs: Sequence[BrollSpec] = (),
    broll_image_paths: Sequence[Path] = (),
    out_width: int = 0,
    out_height: int = 0,
    watermark_path: Path | None = None,
    watermark_position: str = DEFAULT_WATERMARK_POSITION,
    has_audio: bool,
    output_path: Path,
) -> list[str]:
    """Overlays B-roll (if any), burns in captions (if any), composites a
    watermark (if any), mixes in background music (if any), and encodes
    to the final container/codec for `export_format`. `input_path` is
    already cropped/scaled to the target output dimensions (either a
    single concatenated highlight-reel clip, or a crossfaded one) —
    unlike build_full_video_render_command, this function never does
    crop/scale itself.

    Stacking order, innermost to outermost: B-roll overlay -> captions ->
    watermark. Broll before captions: captions must never end up hidden
    behind a full-frame B-roll still. Watermark last, always: nothing
    (captions, B-roll) should be able to obscure brand/attribution.

    `out_width`/`out_height` are required (raises ValueError otherwise)
    whenever `broll_specs` or `watermark_path` is set — B-roll needs them
    to size its Ken Burns zoompan
    (domain.rendering.broll.build_broll_filter_complex), the watermark
    needs `out_width` to scale itself down to a small corner mark instead
    of compositing at its native resolution.
    """
    if (broll_specs or watermark_path) and (out_width <= 0 or out_height <= 0):
        raise ValueError("out_width/out_height are required when broll_specs/watermark_path is set")

    codecs = EXPORT_FORMAT_CODECS.get(export_format, EXPORT_FORMAT_CODECS[DEFAULT_EXPORT_FORMAT])
    needs_complex = bool(music_path or broll_specs or watermark_path)

    cmd = ["ffmpeg", "-y", "-i", str(input_path)]

    if not needs_complex:
        # Unchanged from before music/broll/watermark support: single
        # input, so plain -vf and implicit stream selection are
        # unambiguous. Captions alone don't need -filter_complex.
        if captions_path is not None:
            cmd += ["-vf", f"ass='{_escape_ass_filter_path(captions_path)}'"]
        cmd += codecs["video"]
        cmd += codecs["audio"] if has_audio else ["-an"]
        cmd += [str(output_path)]
        return cmd

    next_index = 1
    music_index: int | None = None
    if music_path is not None:
        cmd += ["-i", str(music_path)]
        music_index = next_index
        next_index += 1

    resolved_broll_specs, next_index = _append_broll_inputs(
        cmd, broll_specs, broll_image_paths, next_index
    )

    watermark_index: int | None = None
    if watermark_path is not None:
        cmd += ["-i", str(watermark_path)]
        watermark_index = next_index
        next_index += 1

    filter_complex_parts: list[str] = []
    video_ref = "0:v"  # unbracketed while still a raw input stream

    broll_fragment = build_broll_filter_complex(
        video_ref, resolved_broll_specs, out_width, out_height
    )
    if broll_fragment:
        filter_complex_parts.append(broll_fragment)
        video_ref = BROLL_OUTPUT_VIDEO_LABEL

    if captions_path is not None:
        filter_complex_parts.append(
            f"[{video_ref}]ass='{_escape_ass_filter_path(captions_path)}'[vcap]"
        )
        video_ref = "vcap"

    if watermark_path is not None:
        assert watermark_index is not None
        filter_complex_parts.append(
            build_watermark_filter_complex(
                video_ref, watermark_index, watermark_position, out_width
            )
        )
        video_ref = "vwatermark"
    video_touched = video_ref != "0:v"

    if music_path is not None:
        if has_audio:
            filter_complex_parts.append(f"[{music_index}:a]volume={MUSIC_MIX_VOLUME}[music]")
            # normalize=0 is deliberate and load-bearing: amix's default
            # normalize=1 would automatically quiet *both* inputs to
            # avoid clipping, silently dropping dialogue volume too.
            # Disabling it, combined with the explicit pre-attenuation on
            # the music input above, is what actually keeps dialogue at
            # full volume with music audibly under it. duration=first
            # anchors the mixed output's length to the dialogue track --
            # the authoritative length from concatenation -- rather than
            # the separately generated (approximately matching) music file.
            filter_complex_parts.append(
                "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
            )
            audio_map: str | None = "[aout]"
        else:
            # No dialogue audio at all -- the generated music is the sole
            # audio output, no mixing needed.
            audio_map = f"{music_index}:a"
    else:
        audio_map = "0:a" if has_audio else None

    cmd += ["-filter_complex", ";".join(filter_complex_parts)]
    cmd += ["-map", f"[{video_ref}]" if video_touched else video_ref]
    if audio_map is not None:
        cmd += ["-map", audio_map]
    cmd += codecs["video"]
    cmd += codecs["audio"] if audio_map is not None else ["-an"]
    cmd += [str(output_path)]
    return cmd


def build_full_video_render_command(
    source_path: Path,
    crop_params: CropParams,
    out_dims: OutputDimensions,
    captions_path: Path | None,
    music_path: Path | None,
    export_format: str,
    *,
    broll_specs: Sequence[BrollSpec] = (),
    broll_image_paths: Sequence[Path] = (),
    watermark_path: Path | None = None,
    watermark_position: str = DEFAULT_WATERMARK_POSITION,
    has_audio: bool,
    output_path: Path,
) -> list[str]:
    """The export_mode="full_video" counterpart to
    build_final_encode_command: a single ffmpeg pass straight from the
    *raw source* (crop/scale + B-roll + captions + watermark + music all
    composed in one -filter_complex), since there's no separate per-clip
    extraction/concatenation step when nothing is being cut. Uses
    FULL_VIDEO_EXPORT_FORMAT_CODECS (a faster libx264 preset) rather than
    EXPORT_FORMAT_CODECS -- see that dict's own docstring for why.
    """
    codecs = FULL_VIDEO_EXPORT_FORMAT_CODECS.get(
        export_format, FULL_VIDEO_EXPORT_FORMAT_CODECS[DEFAULT_EXPORT_FORMAT]
    )
    cmd = ["ffmpeg", "-y", "-i", str(source_path)]
    next_index = 1

    music_index: int | None = None
    if music_path is not None:
        cmd += ["-i", str(music_path)]
        music_index = next_index
        next_index += 1

    resolved_broll_specs, next_index = _append_broll_inputs(
        cmd, broll_specs, broll_image_paths, next_index
    )

    watermark_index: int | None = None
    if watermark_path is not None:
        cmd += ["-i", str(watermark_path)]
        watermark_index = next_index
        next_index += 1

    filter_complex_parts = [
        f"[0:v]crop={crop_params.width}:{crop_params.height}:{crop_params.x}:{crop_params.y},"
        f"scale={out_dims.width}:{out_dims.height}[vscaled]"
    ]
    video_ref = "vscaled"  # always filtered here -- crop/scale always runs

    broll_fragment = build_broll_filter_complex(
        video_ref, resolved_broll_specs, out_dims.width, out_dims.height
    )
    if broll_fragment:
        filter_complex_parts.append(broll_fragment)
        video_ref = BROLL_OUTPUT_VIDEO_LABEL

    if captions_path is not None:
        filter_complex_parts.append(
            f"[{video_ref}]ass='{_escape_ass_filter_path(captions_path)}'[vcap]"
        )
        video_ref = "vcap"

    if watermark_path is not None:
        assert watermark_index is not None
        filter_complex_parts.append(
            build_watermark_filter_complex(
                video_ref, watermark_index, watermark_position, out_dims.width
            )
        )
        video_ref = "vwatermark"

    if music_path is not None:
        if has_audio:
            filter_complex_parts.append(f"[{music_index}:a]volume={MUSIC_MIX_VOLUME}[music]")
            filter_complex_parts.append(
                "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
            )
            audio_map: str | None = "[aout]"
        else:
            audio_map = f"{music_index}:a"
    else:
        audio_map = "0:a" if has_audio else None

    cmd += ["-filter_complex", ";".join(filter_complex_parts)]
    cmd += ["-map", f"[{video_ref}]"]
    if audio_map is not None:
        cmd += ["-map", audio_map]
    cmd += codecs["video"]
    cmd += codecs["audio"] if audio_map is not None else ["-an"]
    cmd += [str(output_path)]
    return cmd
