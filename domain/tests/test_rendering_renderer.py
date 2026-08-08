import subprocess
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from domain.exceptions import PermanentPipelineError
from domain.rendering.renderer import render_video


@dataclass
class _Highlight:
    rank: int
    start_time: float
    end_time: float
    emoji: str | None = None
    transition: str | None = None


@dataclass
class _Segment:
    start_time: float
    end_time: float
    text: str


@dataclass
class _BrollAsset:
    start_time: float
    end_time: float
    image_path: str | None = "/tmp/broll_source.jpg"


def _settings(**overrides):
    base = {
        "export_mode": "highlight_reel",
        "output_duration_seconds": 60,
        "aspect_ratio": "9:16",
        "caption_style": "bold",
        "font": "inter",
        "color_theme": "default",
        "transition_style": "fade",
        "music_style": "none",
        "broll_type": "none",
        "subtitle_language": "auto",
        "video_quality": "1080p",
        "export_format": "mp4",
        "logo_image_path": None,
        "logo_position": "bottom_right",
    }
    base.update(overrides)
    return base


def _ok(returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


def test_render_video_runs_full_pipeline_and_returns_output_path(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]
    segments = [_Segment(start_time=1.0, end_time=3.0, text="hi")]
    progress_calls = []

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        output_path = render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=segments,
            highlights=highlights,
            settings_snapshot=_settings(),
            workdir=tmp_path,
            progress_callback=lambda pct, stage: progress_calls.append((pct, stage)),
        )

    assert output_path == tmp_path / "output.mp4"
    # extract (1 clip) + concat (single clip -> hard cut, nothing to
    # cross-fade with) + final encode = 3 ffmpeg invocations
    assert mock_run.call_count == 3
    assert [c[0][0][0] for c in mock_run.call_args_list] == ["ffmpeg", "ffmpeg", "ffmpeg"]
    stages = [stage for _, stage in progress_calls]
    assert stages == [
        "selecting_clips", "extracting_clips", "building_captions",
        "concatenating", "encoding", "finalizing",
    ]  # fmt: skip
    assert progress_calls[-1][0] == 95


def test_render_video_skips_captions_when_disabled(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(caption_style="none"),
            workdir=tmp_path,
        )

    # Final encode call should have no -vf/ass burn-in.
    final_call_cmd = mock_run.call_args_list[-1][0][0]
    assert "-vf" not in final_call_cmd
    assert not (tmp_path / "captions.ass").exists()


def test_render_video_raises_permanent_error_with_stderr_on_ffmpeg_failure(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]

    with (
        patch("subprocess.run", return_value=_ok(returncode=1, stderr="Unknown encoder 'libx264'")),
        pytest.raises(PermanentPipelineError, match="Unknown encoder"),
    ):
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(),
            workdir=tmp_path,
        )


def test_render_video_raises_permanent_error_when_ffmpeg_missing(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(PermanentPipelineError, match="ffmpeg executable not found"),
    ):
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(),
            workdir=tmp_path,
        )


def test_render_video_raises_permanent_error_on_timeout(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]

    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1800)),
        pytest.raises(PermanentPipelineError, match="timed out"),
    ):
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(),
            workdir=tmp_path,
        )


def test_render_video_generates_and_mixes_music_when_requested(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]
    progress_calls = []

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(music_style="upbeat"),
            workdir=tmp_path,
            progress_callback=lambda pct, stage: progress_calls.append((pct, stage)),
        )

    # extract (1 clip) + concat + music generation + final encode = 4 calls
    assert mock_run.call_count == 4
    stages = [stage for _, stage in progress_calls]
    assert "generating_music" in stages
    music_call_cmd = mock_run.call_args_list[2][0][0]
    assert "music.m4a" in music_call_cmd[-1]
    final_call_cmd = mock_run.call_args_list[-1][0][0]
    assert any("music.m4a" in arg for arg in final_call_cmd)


def test_render_video_skips_music_generation_when_style_is_none(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]
    progress_calls = []

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(music_style="none"),
            workdir=tmp_path,
            progress_callback=lambda pct, stage: progress_calls.append((pct, stage)),
        )

    assert mock_run.call_count == 3  # extract + concat + encode, no music step
    stages = [stage for _, stage in progress_calls]
    assert "generating_music" not in stages


def test_render_video_missing_music_style_key_defaults_to_no_music(tmp_path):
    """settings_snapshot from a RenderJob created before music_style was
    added to SNAPSHOT_FIELDS won't have the key at all -- must not raise.
    """
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]
    settings = _settings()
    del settings["music_style"]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=settings,
            workdir=tmp_path,
        )

    assert mock_run.call_count == 3


def test_render_video_uses_hard_concat_when_transition_style_none(tmp_path):
    highlights = [
        _Highlight(rank=1, start_time=0.0, end_time=10.0),
        _Highlight(rank=2, start_time=20.0, end_time=30.0),
    ]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=40.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(transition_style="none"),
            workdir=tmp_path,
        )

    # extract(2) + concat + encode = 4 -- the concat step is the plain
    # concat-demuxer, not xfade (no -filter_complex for it)
    concat_call_cmd = mock_run.call_args_list[2][0][0]
    assert "-filter_complex" not in concat_call_cmd
    assert "-c" in concat_call_cmd and "copy" in concat_call_cmd


def test_render_video_uses_crossfade_concat_when_transition_style_set_and_multiple_clips(tmp_path):
    highlights = [
        _Highlight(rank=1, start_time=0.0, end_time=10.0),
        _Highlight(rank=2, start_time=20.0, end_time=30.0),
    ]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=40.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(transition_style="fade"),
            workdir=tmp_path,
        )

    concat_call_cmd = mock_run.call_args_list[2][0][0]
    assert "-filter_complex" in concat_call_cmd
    filter_complex = concat_call_cmd[concat_call_cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade" in filter_complex
    assert "acrossfade" in filter_complex


def test_render_video_falls_back_to_hard_concat_for_single_clip_even_with_transition_style_set(
    tmp_path,
):
    """A single surviving clip has nothing to cross-fade with regardless
    of transition_style -- select_clips_for_duration can legitimately
    return exactly one clip.
    """
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(transition_style="fade"),
            workdir=tmp_path,
        )

    concat_call_cmd = mock_run.call_args_list[1][0][0]
    assert "-filter_complex" not in concat_call_cmd
    assert "-c" in concat_call_cmd and "copy" in concat_call_cmd


def test_render_video_composites_broll_when_asset_fully_contained_in_clip(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]
    broll_assets = [_BrollAsset(start_time=2.0, end_time=5.0)]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            broll_assets=broll_assets,
            settings_snapshot=_settings(broll_type="stock_footage"),
            workdir=tmp_path,
        )

    final_call_cmd = mock_run.call_args_list[-1][0][0]
    assert "/tmp/broll_source.jpg" in final_call_cmd
    assert "-loop" in final_call_cmd
    filter_complex = final_call_cmd[final_call_cmd.index("-filter_complex") + 1]
    assert "zoompan" in filter_complex


def test_render_video_skips_broll_when_asset_has_no_downloaded_image(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]
    broll_assets = [_BrollAsset(start_time=2.0, end_time=5.0, image_path=None)]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            broll_assets=broll_assets,
            settings_snapshot=_settings(broll_type="stock_footage"),
            workdir=tmp_path,
        )

    final_call_cmd = mock_run.call_args_list[-1][0][0]
    assert "-loop" not in final_call_cmd


def test_render_video_composites_watermark_when_logo_path_present(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(logo_image_path="/tmp/logo.png"),
            workdir=tmp_path,
        )

    final_call_cmd = mock_run.call_args_list[-1][0][0]
    assert "/tmp/logo.png" in final_call_cmd
    filter_complex = final_call_cmd[final_call_cmd.index("-filter_complex") + 1]
    assert "scale=" in filter_complex  # watermark is scaled down, not composited at full size


def test_render_video_watermark_respects_logo_position_setting(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(logo_image_path="/tmp/logo.png", logo_position="top_left"),
            workdir=tmp_path,
        )

    final_call_cmd = mock_run.call_args_list[-1][0][0]
    filter_complex = final_call_cmd[final_call_cmd.index("-filter_complex") + 1]
    assert "overlay=x=24:y=24" in filter_complex  # top_left, not the bottom_right default


def test_render_video_works_without_progress_callback(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]
    with patch("subprocess.run", return_value=_ok()):
        output_path = render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=10.0,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(),
            workdir=tmp_path,
        )
    assert output_path.name == "output.mp4"


def test_render_video_full_video_mode_skips_clip_selection_and_uses_single_pass(tmp_path):
    progress_calls = []

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        output_path = render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=45.0,
            transcript_segments=[],
            highlights=[],  # export_mode=full_video never touches highlights
            settings_snapshot=_settings(export_mode="full_video"),
            workdir=tmp_path,
            progress_callback=lambda pct, stage: progress_calls.append((pct, stage)),
        )

    assert output_path == tmp_path / "output.mp4"
    assert mock_run.call_count == 1  # a single composed ffmpeg pass, no extract/concat
    stages = [stage for _, stage in progress_calls]
    assert "selecting_clips" not in stages
    assert "extracting_clips" not in stages
    assert "concatenating" not in stages
    only_call_cmd = mock_run.call_args_list[0][0][0]
    assert only_call_cmd[only_call_cmd.index("-i") + 1] == str(tmp_path / "source.mp4")


def test_render_video_full_video_mode_skips_captions_when_disabled(tmp_path):
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=45.0,
            transcript_segments=[],
            highlights=[],
            settings_snapshot=_settings(export_mode="full_video", caption_style="none"),
            workdir=tmp_path,
        )

    only_call_cmd = mock_run.call_args_list[0][0][0]
    assert "-vf" not in only_call_cmd
    assert not (tmp_path / "captions.ass").exists()


def test_render_video_full_video_mode_generates_music_for_whole_duration(tmp_path):
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            video_duration=45.0,
            transcript_segments=[],
            highlights=[],
            settings_snapshot=_settings(export_mode="full_video", music_style="chill"),
            workdir=tmp_path,
        )

    assert mock_run.call_count == 2  # music generation + the single encode pass
    music_call_cmd = mock_run.call_args_list[0][0][0]
    assert "duration=45.000" in " ".join(music_call_cmd)
