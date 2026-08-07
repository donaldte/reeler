from types import SimpleNamespace
from unittest.mock import patch

from domain.scene_detection.providers.pyscenedetect_provider import PySceneDetectProvider


def _timecode(seconds: float):
    return SimpleNamespace(get_seconds=lambda: seconds)


def test_detect_maps_scene_list_to_dtos(tmp_path):
    provider = PySceneDetectProvider(threshold=27.0, min_scene_len_seconds=0.6)
    fake_scene_list = [
        (_timecode(0.0), _timecode(4.2)),
        (_timecode(4.2), _timecode(9.8)),
    ]

    with patch("scenedetect.detect", return_value=fake_scene_list) as mock_detect:
        scenes = provider.detect(tmp_path / "clip.mp4")

    assert mock_detect.called
    assert len(scenes) == 2
    assert scenes[0].index == 0
    assert scenes[0].start == 0.0
    assert scenes[0].end == 4.2
    assert scenes[1].start == 4.2


def test_detect_returns_empty_list_when_no_cuts(tmp_path):
    provider = PySceneDetectProvider()

    with patch("scenedetect.detect", return_value=[]):
        scenes = provider.detect(tmp_path / "clip.mp4")

    assert scenes == []


def test_min_scene_len_frames_computed_from_seconds():
    provider = PySceneDetectProvider(min_scene_len_seconds=1.0, assumed_fps_for_min_len=25.0)
    assert provider.min_scene_len_frames == 25
