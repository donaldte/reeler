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


def _settings(**overrides):
    base = {
        "output_duration_seconds": 60,
        "aspect_ratio": "9:16",
        "caption_style": "bold",
        "font": "inter",
        "color_theme": "default",
        "transition_style": "fade",
        "music_style": "none",
        "subtitle_language": "auto",
        "video_quality": "1080p",
        "export_format": "mp4",
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
            transcript_segments=segments,
            highlights=highlights,
            settings_snapshot=_settings(),
            workdir=tmp_path,
            progress_callback=lambda pct, stage: progress_calls.append((pct, stage)),
        )

    assert output_path == tmp_path / "output.mp4"
    # extract (1 clip) + concat + final encode = 3 ffmpeg invocations
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
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=settings,
            workdir=tmp_path,
        )

    assert mock_run.call_count == 3


def test_render_video_per_clip_transition_cut_skips_fade_for_that_clip(tmp_path):
    highlights = [
        _Highlight(rank=1, start_time=0.0, end_time=10.0, transition="cut"),
        _Highlight(rank=2, start_time=20.0, end_time=30.0, transition=None),
    ]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(transition_style="fade"),  # transitions on globally
            workdir=tmp_path,
        )

    extract_calls = mock_run.call_args_list[:2]
    first_clip_vf = extract_calls[0][0][0][extract_calls[0][0][0].index("-vf") + 1]
    second_clip_vf = extract_calls[1][0][0][extract_calls[1][0][0].index("-vf") + 1]
    assert "fade" not in first_clip_vf  # explicit "cut" suggestion skips the fade
    assert "fade" in second_clip_vf  # no suggestion -> defaults to fading


def test_render_video_transition_style_none_disables_fades_even_if_highlight_suggests_fade(
    tmp_path,
):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0, transition="fade")]

    with patch("subprocess.run", return_value=_ok()) as mock_run:
        render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(transition_style="none"),  # master switch off
            workdir=tmp_path,
        )

    extract_cmd = mock_run.call_args_list[0][0][0]
    vf = extract_cmd[extract_cmd.index("-vf") + 1]
    assert "fade" not in vf


def test_render_video_works_without_progress_callback(tmp_path):
    highlights = [_Highlight(rank=1, start_time=0.0, end_time=10.0)]
    with patch("subprocess.run", return_value=_ok()):
        output_path = render_video(
            source_path=tmp_path / "source.mp4",
            source_width=1920,
            source_height=1080,
            has_audio=True,
            transcript_segments=[],
            highlights=highlights,
            settings_snapshot=_settings(),
            workdir=tmp_path,
        )
    assert output_path.name == "output.mp4"
