import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from domain.exceptions import UnsupportedMediaError
from domain.media.ffprobe import probe

FFPROBE_JSON = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30000/1001",
        },
        {"codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "12.345", "size": "1048576"},
}


def _completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_probe_parses_video_and_audio_streams(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    with patch("subprocess.run", return_value=_completed(json.dumps(FFPROBE_JSON))):
        meta = probe(video)

    assert meta.duration_seconds == pytest.approx(12.345)
    assert meta.width == 1920
    assert meta.height == 1080
    assert meta.fps == pytest.approx(29.97, abs=0.01)
    assert meta.has_audio is True
    assert meta.video_codec == "h264"
    assert meta.audio_codec == "aac"
    assert meta.file_size_bytes == 1048576


def test_probe_no_audio_stream(tmp_path: Path):
    video = tmp_path / "silent.mp4"
    video.write_bytes(b"fake")
    payload = {**FFPROBE_JSON, "streams": [FFPROBE_JSON["streams"][0]]}

    with patch("subprocess.run", return_value=_completed(json.dumps(payload))):
        meta = probe(video)

    assert meta.has_audio is False
    assert meta.audio_codec is None


def test_probe_raises_on_missing_video_stream(tmp_path: Path):
    video = tmp_path / "audio_only.mp3"
    video.write_bytes(b"fake")
    payload = {"streams": [FFPROBE_JSON["streams"][1]], "format": {}}

    with (
        patch("subprocess.run", return_value=_completed(json.dumps(payload))),
        pytest.raises(UnsupportedMediaError, match="no video stream"),
    ):
        probe(video)


def test_probe_raises_on_nonzero_exit(tmp_path: Path):
    video = tmp_path / "corrupt.mp4"
    video.write_bytes(b"fake")

    with (
        patch("subprocess.run", return_value=_completed("", returncode=1, stderr="invalid data")),
        pytest.raises(UnsupportedMediaError, match="could not read"),
    ):
        probe(video)


def test_probe_raises_when_ffprobe_missing(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(UnsupportedMediaError, match="ffprobe executable not found"),
    ):
        probe(video)


def test_probe_raises_on_timeout(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)),
        pytest.raises(UnsupportedMediaError, match="timed out"),
    ):
        probe(video)


def test_probe_raises_on_invalid_json(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    with (
        patch("subprocess.run", return_value=_completed("not json")),
        pytest.raises(UnsupportedMediaError, match="invalid JSON"),
    ):
        probe(video)
