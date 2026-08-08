"""Generates a short procedural background-music bed with ffmpeg's own
`lavfi` synthetic audio sources — no downloaded/bundled audio files.

This is a deliberate, disclosed simplification, not a substitute for
curated real music: bundling downloaded "royalty-free" tracks would bloat
the repo and require verifying real licensing terms, which is out of
scope here, and it would break the project's local-first/fully-offline
ethos (no external downloads at render time). Instead, each `music_style`
maps to a small root-note chord (a few sine waves) layered together and
shaped with `tremolo` (adds movement so it doesn't sound like a dead
test tone) and a `lowpass` filter (softens the harsh edges of pure sine
waves) — a simple ambient pad, not a real composed track. See
docs/roadmap.md.
"""

from pathlib import Path

# root: fundamental frequency (Hz) of the chord. chord_ratios: frequency
# multipliers layered on top of root (1.0 = root note itself). tremolo_hz:
# amplitude-modulation rate — low values read as a slow ambient swell,
# higher values as a more energetic pulse. lowpass_hz: cutoff that softens
# the sine waves' otherwise harsh, synthetic edge.
MUSIC_STYLE_PARAMS: dict[str, dict[str, float | list[float]]] = {
    "upbeat": {
        "root": 220.0, "chord_ratios": [1.0, 1.25, 1.5], "tremolo_hz": 4.0, "lowpass_hz": 4000
    },
    "chill": {
        "root": 174.61, "chord_ratios": [1.0, 1.2, 1.5], "tremolo_hz": 0.3, "lowpass_hz": 1800
    },
    "dramatic": {
        "root": 98.0, "chord_ratios": [1.0, 1.19, 1.5], "tremolo_hz": 0.15, "lowpass_hz": 1200
    },
    "corporate": {
        "root": 196.0, "chord_ratios": [1.0, 1.25, 1.5], "tremolo_hz": 1.0, "lowpass_hz": 3000
    },
    "cinematic": {
        "root": 110.0, "chord_ratios": [1.0, 1.5, 2.0], "tremolo_hz": 0.2, "lowpass_hz": 2500
    },
}  # fmt: skip

# Cap on the in/out fade so a very short target duration never produces a
# negative or overlapping fade window (fade_out_start would go below 0).
MAX_FADE_SECONDS = 1.5


def build_music_generation_command(
    music_style: str, duration: float, output_path: Path
) -> list[str]:
    """Builds the argv for a standalone ffmpeg invocation that synthesizes
    `duration` seconds of background music into `output_path` (AAC).

    Pure command construction only — no subprocess call here, see
    domain/rendering/renderer.py, same pattern as every other builder in
    this package.

    Raises:
        ValueError: unknown `music_style`, or `duration <= 0`.
    """
    if music_style not in MUSIC_STYLE_PARAMS:
        raise ValueError(f"Unknown music_style: {music_style!r}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration!r}")

    params = MUSIC_STYLE_PARAMS[music_style]
    root = params["root"]
    assert isinstance(root, float)
    ratios = params["chord_ratios"]
    assert isinstance(ratios, list)
    tremolo_hz = params["tremolo_hz"]
    lowpass_hz = params["lowpass_hz"]

    fade_duration = min(MAX_FADE_SECONDS, duration / 4)
    fade_out_start = max(0.0, duration - fade_duration)

    cmd = ["ffmpeg", "-y"]
    for ratio in ratios:
        freq = root * ratio
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={freq:.3f}:duration={duration:.3f}"]

    input_labels = "".join(f"[{i}:a]" for i in range(len(ratios)))
    filter_complex = (
        f"{input_labels}amix=inputs={len(ratios)}:duration=first:dropout_transition=0,"
        f"tremolo=f={tremolo_hz}:d=0.4,"
        f"lowpass=f={lowpass_hz},"
        f"afade=t=in:st=0:d={fade_duration:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_duration:.3f}"
        "[out]"
    )
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]  # fmt: skip
    return cmd
