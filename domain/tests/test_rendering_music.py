from pathlib import Path

import pytest

from domain.rendering.music import MUSIC_STYLE_PARAMS, build_music_generation_command


def test_unknown_style_raises_value_error():
    with pytest.raises(ValueError, match="Unknown music_style"):
        build_music_generation_command("dubstep", 30.0, Path("/tmp/music.m4a"))


def test_non_positive_duration_raises_value_error():
    with pytest.raises(ValueError, match="duration must be positive"):
        build_music_generation_command("chill", 0.0, Path("/tmp/music.m4a"))


def test_command_shape_for_each_known_style():
    for style, params in MUSIC_STYLE_PARAMS.items():
        cmd = build_music_generation_command(style, 30.0, Path("/tmp/music.m4a"))
        assert cmd[0] == "ffmpeg"
        # one `-f lavfi -i sine=...` pair per chord ratio
        ratios = params["chord_ratios"]
        assert cmd.count("lavfi") == len(ratios)
        root = params["root"]
        for ratio in ratios:
            expected_freq = f"{root * ratio:.3f}"
            assert any(f"frequency={expected_freq}" in arg for arg in cmd), style
            assert any("duration=30.000" in arg for arg in cmd), style
        assert "-c:a" in cmd and "aac" in cmd
        assert cmd[-1] == "/tmp/music.m4a"


def test_filter_complex_includes_tremolo_lowpass_and_fades():
    cmd = build_music_generation_command("cinematic", 20.0, Path("/tmp/music.m4a"))
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    params = MUSIC_STYLE_PARAMS["cinematic"]
    assert f"amix=inputs={len(params['chord_ratios'])}" in filter_complex
    assert f"tremolo=f={params['tremolo_hz']}" in filter_complex
    assert f"lowpass=f={params['lowpass_hz']}" in filter_complex
    assert "afade=t=in:st=0:d=" in filter_complex
    assert "afade=t=out:st=" in filter_complex
    assert filter_complex.endswith("[out]")
    assert "-map" in cmd
    assert cmd[cmd.index("-map") + 1] == "[out]"


def test_fade_duration_capped_for_long_tracks():
    cmd = build_music_generation_command("chill", 120.0, Path("/tmp/music.m4a"))
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    # MAX_FADE_SECONDS = 1.5 -- a long track should not use a much longer fade
    assert "afade=t=in:st=0:d=1.500" in filter_complex


def test_fade_duration_shrinks_for_short_tracks():
    cmd = build_music_generation_command("chill", 4.0, Path("/tmp/music.m4a"))
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    # duration/4 = 1.0s, below the MAX_FADE_SECONDS cap
    assert "afade=t=in:st=0:d=1.000" in filter_complex
    assert "afade=t=out:st=3.000:d=1.000" in filter_complex
