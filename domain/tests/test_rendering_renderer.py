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
