"""Pure ffmpeg filter_complex fragment builder for B-roll still-image
overlays with a Ken Burns pan/zoom, plus the pure-Python remapping step
that turns `BrollAsset` rows (expressed on the *source* video's timeline)
into `BrollSpec`s (expressed on the final *output* timeline) — no
subprocess calls anywhere in this module, same pattern as
domain/rendering/ffmpeg_commands.py.

Caller (renderer.py) is responsible for adding each B-roll image as its
own ffmpeg input (`-loop 1 -framerate {BROLL_FPS} -i <path>`, in the same
order as `BrollSpec.image_input_index` values) *before* the fragment
returned by `build_broll_filter_complex` is spliced into the larger
`-filter_complex` string.
"""

from collections.abc import Sequence
from itertools import pairwise
from typing import Protocol

from domain.rendering.dto import BrollSpec, ClipSpec

# zoompan's own output frame rate for the synthesized Ken Burns clip. Not
# threaded through as a single pipeline-wide output FPS (nothing else in
# domain/rendering pins one — clips inherit whatever framerate the single
# source_path already has) — overlay tolerates a framerate mismatch
# between the base video and this layer fine (it samples the overlay
# branch at each base-video timestamp), so this only needs to be high
# enough for a smooth zoom, not matched to the source.
BROLL_FPS = 30

# Crossfade at each B-roll window's edges, so it appears/disappears
# smoothly rather than as a hard cut. Same fade_out_start = max(0,
# duration - X) idiom as ffmpeg_commands' clip-level fades used to use.
BROLL_CROSSFADE_SECONDS = 0.4

# Per-frame zoom increment and cap. Small enough that even a long B-roll
# window doesn't zoom in absurdly far — ~0.0015/frame at 30fps is a slow,
# barely-perceptible Ken Burns rate.
ZOOM_STEP = 0.0015
ZOOM_MAX = 1.5

# zoom_expr seeds explicitly off zoompan's `on` (output frame number) via
# `if(eq(on,0),...)` rather than relying on the filter's own default
# initial zoom value — deterministic regardless of ffmpeg build/version.
# x_expr/y_expr keep the crop window centered as zoom changes — the
# canonical idiom from zoompan's own filter documentation.
ZOOM_DIRECTION_PARAMS: dict[str, dict[str, str]] = {
    "in": {
        "zoom_expr": f"if(eq(on,0),1.0,min(zoom+{ZOOM_STEP},{ZOOM_MAX}))",
        "x_expr": "iw/2-(iw/zoom/2)",
        "y_expr": "ih/2-(ih/zoom/2)",
    },
    "out": {
        "zoom_expr": f"if(eq(on,0),{ZOOM_MAX},max(zoom-{ZOOM_STEP},1.0))",
        "x_expr": "iw/2-(iw/zoom/2)",
        "y_expr": "ih/2-(ih/zoom/2)",
    },
}
DEFAULT_ZOOM_DIRECTION = "in"

# Pre-scale factor applied before zoompan crops into the image — gives
# zoompan headroom to zoom into real source pixels rather than upscaling
# an already-output-sized frame (which would look soft at ZOOM_MAX). A
# quality choice, not a correctness requirement.
BROLL_PRESCALE_FACTOR = 2

# Deterministic final video output label of the returned fragment,
# regardless of how many broll_specs were composited — lets callers
# splice this fragment into a larger graph without needing its internals.
BROLL_OUTPUT_VIDEO_LABEL = "vbroll"


def build_broll_filter_complex(
    base_video_label: str,
    broll_specs: Sequence[BrollSpec],
    out_width: int,
    out_height: int,
) -> str:
    """Returns a filter_complex fragment (joinable with `;` into a larger
    graph) that overlays each B-roll window full-frame over
    `base_video_label` for its [start, end) window, with a Ken Burns
    zoom/pan and a BROLL_CROSSFADE_SECONDS crossfade in/out at each
    window's edges. Outside all windows, the base video passes through
    untouched.

    On success (non-empty `broll_specs`), the fragment's final video
    output is always `[{BROLL_OUTPUT_VIDEO_LABEL}]`. If `broll_specs` is
    empty, returns "" — caller must then use `base_video_label` itself as
    the video source for the next stage.

    Raises:
        ValueError: any window has end <= start, or two windows overlap
            (B-roll windows must be non-overlapping — overlay's `enable=`
            gate has no defined behavior for simultaneously-true windows
            on two different layers chained this way).
            `domain.rendering.broll.remap_broll_to_output_timeline`
            already defensively drops overlaps before they reach here —
            this check is a safety net for any other caller.
    """
    if not broll_specs:
        return ""

    ordered = sorted(broll_specs, key=lambda b: b.start)
    for spec in ordered:
        if spec.end <= spec.start:
            raise ValueError(f"Invalid B-roll window: start={spec.start}, end={spec.end}")
    for prev, nxt in pairwise(ordered):
        if nxt.start < prev.end:
            raise ValueError(f"Overlapping B-roll windows: {prev} and {nxt}")

    pre_w = out_width * BROLL_PRESCALE_FACTOR
    pre_h = out_height * BROLL_PRESCALE_FACTOR

    parts: list[str] = []
    prev_label = base_video_label
    last_index = len(ordered) - 1
    for i, spec in enumerate(ordered):
        win_dur = spec.duration
        d_frames = max(1, round(win_dur * BROLL_FPS))
        fade_out_start = max(0.0, win_dur - BROLL_CROSSFADE_SECONDS)
        zoom = ZOOM_DIRECTION_PARAMS.get(
            spec.zoom_direction, ZOOM_DIRECTION_PARAMS[DEFAULT_ZOOM_DIRECTION]
        )
        layer_label = f"broll{i}"
        stage_label = BROLL_OUTPUT_VIDEO_LABEL if i == last_index else f"bv{i}"

        # force_original_aspect_ratio=increase + crop: avoids stretching a
        # B-roll image whose aspect ratio doesn't match the output —
        # scales so the *smaller* dimension fills, then center-crops the
        # overflow (same "crop to target ratio" idea as
        # dimensions.compute_crop_params, just done in-filter here).
        parts.append(
            f"[{spec.image_input_index}:v]"
            f"scale={pre_w}:{pre_h}:force_original_aspect_ratio=increase,"
            f"crop={pre_w}:{pre_h},"
            f"zoompan=z='{zoom['zoom_expr']}':x='{zoom['x_expr']}':y='{zoom['y_expr']}':"
            f"d={d_frames}:s={out_width}x{out_height}:fps={BROLL_FPS},"
            f"trim=duration={win_dur:.3f},"
            "setpts=PTS-STARTPTS,"
            "format=yuva420p,"
            f"fade=t=in:st=0:d={BROLL_CROSSFADE_SECONDS}:alpha=1,"
            f"fade=t=out:st={fade_out_start:.3f}:d={BROLL_CROSSFADE_SECONDS}:alpha=1,"
            f"setpts=PTS+{spec.start:.3f}/TB"
            f"[{layer_label}]"
        )
        # enable=between(...) is load-bearing, not redundant with the
        # branch's own trim: without it, overlay would freeze the last
        # frame of the (already-ended) B-roll branch over the base video
        # for the rest of the render (overlay's default repeatlast=1
        # behavior), not just show the base video again.
        parts.append(
            f"[{prev_label}][{layer_label}]"
            f"overlay=enable='between(t,{spec.start:.3f},{spec.end:.3f})'"
            f"[{stage_label}]"
        )
        prev_label = stage_label

    return ";".join(parts)


class BrollAssetLike(Protocol):
    """Structural type so this module doesn't need to import the Django
    `BrollAsset` model (domain/ stays framework-free) — mirrors
    HighlightLike/TranscriptSegmentLike elsewhere in domain/rendering/.

    `image_path` (a plain string, not a Django FieldFile) is what keeps
    this framework-free while still letting the real ORM model satisfy
    it structurally — see `apps.highlights.models.BrollAsset.image_path`.
    """

    start_time: float
    end_time: float

    # A read-only `@property` here, not a plain attribute annotation:
    # the real model (apps.highlights.models.BrollAsset.image_path) is a
    # read-only property, and a plain `image_path: str | None`
    # annotation would require a *settable* attribute to satisfy this
    # Protocol structurally, which mypy correctly rejects.
    @property
    def image_path(self) -> str | None: ...


def remap_broll_to_output_timeline(
    broll_assets: Sequence[BrollAssetLike], clips: Sequence[ClipSpec]
) -> list[tuple[BrollAssetLike, BrollSpec]]:
    """Remaps each B-roll asset's [start_time, end_time] (on the *source*
    video's timeline) onto the final concatenated-clip *output* timeline —
    the same cumulative-offset idea as
    domain.rendering.captions.build_ass_captions's segment remapping, just
    producing BrollSpecs instead of ASS dialogue lines.

    An asset is included only if it's **fully contained** within a single
    surviving clip — a deliberate simplification: windows straddling a
    clip boundary, or spanning two separate highlights, are dropped
    rather than split. For full-video-mode renders this is trivial (one
    synthetic `ClipSpec(0, video_duration, ...)` — full 1:1 passthrough).

    Also defensively drops any remapped window that would overlap an
    already-accepted one (greedy, earliest-start-wins) — the analysis
    prompt asks the LLM for non-overlapping suggestions, but nothing
    enforces that at the schema level, and a render should never crash
    over a bad AI suggestion (build_broll_filter_complex itself still
    raises on overlap, as a safety net for any other caller).

    Returns (surviving_asset, remapped_spec) pairs, in output-timeline
    order. `BrollSpec.image_input_index` values here are just 0-based
    placeholders (matching each pair's position in the returned list) —
    the *real* ffmpeg input index depends on how many other inputs
    (source video, music, watermark) the caller adds first, so
    `domain.rendering.ffmpeg_commands._append_broll_inputs` re-derives
    the actual index when it appends each image as an ffmpeg input;
    nothing here needs to predict that.
    """
    candidates: list[tuple[BrollAssetLike, float, float]] = []
    cumulative_offset = 0.0
    for clip in clips:
        for asset in broll_assets:
            if asset.start_time >= clip.start and asset.end_time <= clip.end:
                new_start = cumulative_offset + (asset.start_time - clip.start)
                new_end = cumulative_offset + (asset.end_time - clip.start)
                candidates.append((asset, new_start, new_end))
        cumulative_offset += clip.duration

    candidates.sort(key=lambda c: c[1])

    accepted: list[tuple[BrollAssetLike, float, float]] = []
    last_end = float("-inf")
    for asset, new_start, new_end in candidates:
        if new_start < last_end:
            continue  # overlaps the previously-accepted window -- drop
        accepted.append((asset, new_start, new_end))
        last_end = new_end

    return [
        (asset, BrollSpec(image_input_index=i, start=start, end=end))
        for i, (asset, start, end) in enumerate(accepted)
    ]
