from dataclasses import dataclass

import pytest

from domain.rendering.broll import build_broll_filter_complex, remap_broll_to_output_timeline
from domain.rendering.dto import BrollSpec, ClipSpec


@dataclass
class _BrollAsset:
    start_time: float
    end_time: float
    image_path: str | None = "/tmp/asset.jpg"


def test_empty_specs_returns_empty_string():
    assert build_broll_filter_complex("0:v", [], 1080, 1920) == ""


def test_single_window_exact_filter_string():
    spec = BrollSpec(image_input_index=2, start=5.0, end=8.5, zoom_direction="in")
    fragment = build_broll_filter_complex("0:v", [spec], 1080, 1920)

    assert fragment == (
        "[2:v]scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
        "zoompan=z='if(eq(on,0),1.0,min(zoom+0.0015,1.5))':x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':d=105:s=1080x1920:fps=30,trim=duration=3.500,"
        "setpts=PTS-STARTPTS,format=yuva420p,fade=t=in:st=0:d=0.4:alpha=1,"
        "fade=t=out:st=3.100:d=0.4:alpha=1,setpts=PTS+5.000/TB[broll0];"
        "[0:v][broll0]overlay=enable='between(t,5.000,8.500)'[vbroll]"
    )


def test_zoom_direction_out_uses_reverse_zoom_expression():
    spec = BrollSpec(image_input_index=0, start=0.0, end=2.0, zoom_direction="out")
    fragment = build_broll_filter_complex("0:v", [spec], 100, 100)
    assert "if(eq(on,0),1.5,max(zoom-0.0015,1.0))" in fragment


def test_unknown_zoom_direction_falls_back_to_default():
    spec = BrollSpec(image_input_index=0, start=0.0, end=2.0, zoom_direction="sideways")
    fragment = build_broll_filter_complex("0:v", [spec], 100, 100)
    assert "if(eq(on,0),1.0,min(zoom" in fragment  # same as "in" (the default)


def test_multiple_windows_chain_through_intermediate_labels():
    specs = [
        BrollSpec(image_input_index=1, start=0.0, end=2.0),
        BrollSpec(image_input_index=2, start=5.0, end=7.0),
    ]
    fragment = build_broll_filter_complex("0:v", specs, 100, 100)
    # first window overlays onto the raw base video, producing an
    # intermediate stage; the second overlays onto *that* stage, and only
    # the last uses the deterministic BROLL_OUTPUT_VIDEO_LABEL
    assert "[0:v][broll0]overlay=enable='between(t,0.000,2.000)'[bv0]" in fragment
    assert "[bv0][broll1]overlay=enable='between(t,5.000,7.000)'[vbroll]" in fragment


def test_end_before_start_raises():
    spec = BrollSpec(image_input_index=0, start=5.0, end=3.0)
    with pytest.raises(ValueError, match="Invalid B-roll window"):
        build_broll_filter_complex("0:v", [spec], 100, 100)


def test_overlapping_windows_raise():
    specs = [
        BrollSpec(image_input_index=0, start=0.0, end=5.0),
        BrollSpec(image_input_index=1, start=3.0, end=8.0),
    ]
    with pytest.raises(ValueError, match="Overlapping B-roll windows"):
        build_broll_filter_complex("0:v", specs, 100, 100)


def test_remap_includes_asset_fully_contained_in_a_clip():
    assets = [_BrollAsset(start_time=12.0, end_time=15.0)]
    clips = [ClipSpec(start=10.0, end=20.0, rank=1)]

    remapped = remap_broll_to_output_timeline(assets, clips)

    assert len(remapped) == 1
    asset, spec = remapped[0]
    assert asset is assets[0]
    # 12-10=2s into the clip, clip starts at output timeline 0
    assert spec.start == 2.0
    assert spec.end == 5.0
    assert spec.image_input_index == 0


def test_remap_offsets_by_cumulative_prior_clip_duration():
    assets = [_BrollAsset(start_time=51.0, end_time=53.0)]
    clips = [
        ClipSpec(start=0.0, end=10.0, rank=1),  # 10s clip -> output [0, 10)
        ClipSpec(start=50.0, end=60.0, rank=2),  # next clip starts at output offset 10
    ]

    remapped = remap_broll_to_output_timeline(assets, clips)

    assert len(remapped) == 1
    _, spec = remapped[0]
    # 51-50=1s into its clip, offset by 10s from the first clip -> starts at 11s
    assert spec.start == 11.0
    assert spec.end == 13.0


def test_remap_drops_asset_not_fully_contained_in_any_clip():
    # starts before the clip and ends after it -- straddles the boundary
    assets = [_BrollAsset(start_time=8.0, end_time=25.0)]
    clips = [ClipSpec(start=10.0, end=20.0, rank=1)]

    assert remap_broll_to_output_timeline(assets, clips) == []


def test_remap_drops_asset_outside_any_clip():
    assets = [_BrollAsset(start_time=100.0, end_time=105.0)]
    clips = [ClipSpec(start=0.0, end=10.0, rank=1)]

    assert remap_broll_to_output_timeline(assets, clips) == []


def test_remap_drops_overlapping_candidates_greedily():
    """The analysis prompt asks for non-overlapping suggestions, but
    nothing enforces that at the schema level -- two overlapping asset
    windows within the same clip must not both survive (that would raise
    inside build_broll_filter_complex downstream).
    """
    assets = [
        _BrollAsset(start_time=2.0, end_time=6.0),
        _BrollAsset(start_time=4.0, end_time=8.0),  # overlaps the first
    ]
    clips = [ClipSpec(start=0.0, end=10.0, rank=1)]

    remapped = remap_broll_to_output_timeline(assets, clips)

    assert len(remapped) == 1
    asset, spec = remapped[0]
    assert asset is assets[0]  # earliest-start wins
    assert (spec.start, spec.end) == (2.0, 6.0)


def test_remap_assigns_sequential_placeholder_indices():
    assets = [
        _BrollAsset(start_time=1.0, end_time=2.0),
        _BrollAsset(start_time=5.0, end_time=6.0),
    ]
    clips = [ClipSpec(start=0.0, end=10.0, rank=1)]

    remapped = remap_broll_to_output_timeline(assets, clips)

    assert [spec.image_input_index for _, spec in remapped] == [0, 1]


def test_remap_empty_inputs_returns_empty_list():
    assert remap_broll_to_output_timeline([], []) == []
    assert remap_broll_to_output_timeline([_BrollAsset(0.0, 1.0)], []) == []
