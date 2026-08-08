"""Pure ffmpeg argv builders — no subprocess calls here (see
domain/rendering/renderer.py for execution). Every function returns a
plain `list[str]` so it's fully unit-testable without ffmpeg installed.
"""

from pathlib import Path

from domain.rendering.dto import ClipSpec, CropParams, OutputDimensions

FADE_DURATION_SECONDS = 0.3

# Fixed pre-attenuation applied to the generated music track before mixing
# it under dialogue — a static mix, not true ducking (no sidechain
# analysis of speech level), but enough to keep music from competing with
# dialogue. See build_final_encode_command's `amix` usage below for why
# this alone isn't sufficient without also disabling amix's normalize.
MUSIC_MIX_VOLUME = 0.25

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


def build_extract_clip_command(
    source_path: Path,
    clip: ClipSpec,
    crop_params: CropParams,
    out_dims: OutputDimensions,
    *,
    has_audio: bool,
    apply_fade: bool,
    output_path: Path,
) -> list[str]:
    """Extracts one highlight from the source video, cropped/scaled to the
    target aspect ratio and resolution. Always re-encodes (crop/scale
    can't be done with stream copy) using the same codec/settings for
    every clip, which is what makes the later concat-demuxer step safe to
    use `-c copy`.

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
    audio_filters: list[str] = []
    if apply_fade:
        fade_out_start = max(0.0, clip.duration - FADE_DURATION_SECONDS)
        filters.append(f"fade=t=in:st=0:d={FADE_DURATION_SECONDS}")
        filters.append(f"fade=t=out:st={fade_out_start:.3f}:d={FADE_DURATION_SECONDS}")
        if has_audio:
            audio_filters.append(f"afade=t=in:st=0:d={FADE_DURATION_SECONDS}")
            audio_filters.append(f"afade=t=out:st={fade_out_start:.3f}:d={FADE_DURATION_SECONDS}")

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
        if audio_filters:
            cmd += ["-af", ",".join(audio_filters)]
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


def _escape_ass_filter_path(path: Path) -> str:
    # libass filter argument escaping: backslashes and colons are special
    # inside ffmpeg filter option strings.
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def build_final_encode_command(
    input_path: Path,
    captions_path: Path | None,
    music_path: Path | None,
    export_format: str,
    *,
    has_audio: bool,
    output_path: Path,
) -> list[str]:
    """Burns in captions (if any), mixes in background music (if any), and
    encodes to the final container/codec for `export_format`.
    """
    codecs = EXPORT_FORMAT_CODECS.get(export_format, EXPORT_FORMAT_CODECS[DEFAULT_EXPORT_FORMAT])
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]

    if music_path is None:
        # Unchanged from before music support: single input, so plain -vf
        # and implicit stream selection are unambiguous.
        if captions_path is not None:
            cmd += ["-vf", f"ass='{_escape_ass_filter_path(captions_path)}'"]
        cmd += codecs["video"]
        cmd += codecs["audio"] if has_audio else ["-an"]
        cmd += [str(output_path)]
        return cmd

    # Two inputs from here on (dialogue + generated music) -- explicit
    # -map for every stream rather than relying on ffmpeg's default
    # stream-selection heuristic, which is not guaranteed to pick the
    # dialogue video/audio over the music input's.
    cmd += ["-i", str(music_path)]
    filter_complex_parts: list[str] = []
    video_map = "0:v"
    if captions_path is not None:
        filter_complex_parts.append(f"[0:v]ass='{_escape_ass_filter_path(captions_path)}'[vout]")
        video_map = "[vout]"

    if has_audio:
        filter_complex_parts.append(f"[1:a]volume={MUSIC_MIX_VOLUME}[music]")
        # normalize=0 is deliberate and load-bearing: amix's default
        # normalize=1 would automatically quiet *both* inputs to avoid
        # clipping, silently dropping dialogue volume too. Disabling it,
        # combined with the explicit pre-attenuation on the music input
        # above, is what actually keeps dialogue at full volume with
        # music audibly under it. duration=first anchors the mixed
        # output's length to the dialogue track -- the authoritative
        # length from concatenation -- rather than the separately
        # generated (approximately matching) music file.
        filter_complex_parts.append(
            "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
        )
        audio_map = "[aout]"
    else:
        # No dialogue audio at all -- the generated music is the sole
        # audio output, no mixing needed.
        audio_map = "1:a"

    if filter_complex_parts:
        cmd += ["-filter_complex", ";".join(filter_complex_parts)]
    cmd += ["-map", video_map, "-map", audio_map]
    cmd += codecs["video"]
    cmd += codecs["audio"]
    cmd += [str(output_path)]
    return cmd
