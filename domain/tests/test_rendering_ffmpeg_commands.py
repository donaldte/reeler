from pathlib import Path

import pytest

from domain.rendering.dto import BrollSpec, ClipSpec, CropParams, OutputDimensions
from domain.rendering.ffmpeg_commands import (
    build_concat_command,
    build_concat_list_content,
    build_crossfade_concat_command,
    build_extract_clip_command,
    build_final_encode_command,
    build_full_video_render_command,
    build_watermark_filter_complex,
)


def test_extract_clip_command_basic_shape():
    cmd = build_extract_clip_command(
        Path("/media/source.mp4"),
        ClipSpec(start=10.0, end=20.0, rank=1),
        CropParams(width=1080, height=1080, x=100, y=0),
        OutputDimensions(1080, 1920),
        has_audio=True,
        output_path=Path("/tmp/clip_000.mp4"),
    )

    assert cmd[0] == "ffmpeg"
    assert "-ss" in cmd
    assert cmd[cmd.index("-ss") + 1] == "10.000"
    assert "-to" in cmd
    assert cmd[cmd.index("-to") + 1] == "20.000"
    # -ss/-to must both come before -i (input seeking, unambiguous semantics)
    assert cmd.index("-ss") < cmd.index("-i")
    assert cmd.index("-to") < cmd.index("-i")
    assert cmd[cmd.index("-i") + 1] == "/media/source.mp4"
    vf = cmd[cmd.index("-vf") + 1]
    assert "crop=1080:1080:100:0" in vf
    assert "scale=1080:1920" in vf
    assert "fade" not in vf  # per-clip fade was removed -- see build_crossfade_concat_command
    assert "-c:a" in cmd and "aac" in cmd
    assert cmd[-1] == "/tmp/clip_000.mp4"


def test_extract_clip_command_no_audio_adds_an_flag():
    cmd = build_extract_clip_command(
        Path("/media/source.mp4"),
        ClipSpec(start=0.0, end=5.0, rank=1),
        CropParams(width=100, height=100, x=0, y=0),
        OutputDimensions(100, 100),
        has_audio=False,
        output_path=Path("/tmp/clip.mp4"),
    )
    assert "-an" in cmd
    assert "-c:a" not in cmd


def test_concat_list_content_format():
    content = build_concat_list_content([Path("/tmp/a.mp4"), Path("/tmp/b.mp4")])
    assert content == "file '/tmp/a.mp4'\nfile '/tmp/b.mp4'\n"


def test_concat_list_content_escapes_single_quotes():
    content = build_concat_list_content([Path("/tmp/it's.mp4")])
    assert content == "file '/tmp/it'\\''s.mp4'\n"


def test_concat_command_uses_demuxer_and_stream_copy():
    cmd = build_concat_command(Path("/tmp/list.txt"), Path("/tmp/out.mp4"))
    assert cmd == [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", "/tmp/list.txt", "-c", "copy", "/tmp/out.mp4",
    ]  # fmt: skip


def test_crossfade_concat_command_requires_at_least_two_clips():
    with pytest.raises(ValueError, match="at least 2 clips"):
        build_crossfade_concat_command(
            [Path("/tmp/a.mp4")], [8.0], has_audio=True, output_path=Path("/tmp/out.mp4")
        )


def test_crossfade_concat_command_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        build_crossfade_concat_command(
            [Path("/tmp/a.mp4"), Path("/tmp/b.mp4")],
            [8.0],
            has_audio=True,
            output_path=Path("/tmp/out.mp4"),
        )


def test_crossfade_concat_command_three_clips_worked_example():
    """Regression test for the documented cumulative-offset math: 3 clips
    of 8s/12s/6s with a 0.5s crossfade must produce offsets 7.5 and 19.0
    (not 20.0 -- the common mistake of using the raw, un-shrunk sum).
    """
    cmd = build_crossfade_concat_command(
        [Path("/tmp/a.mp4"), Path("/tmp/b.mp4"), Path("/tmp/c.mp4")],
        [8.0, 12.0, 6.0],
        has_audio=True,
        crossfade_duration=0.5,
        transition="fade",
        output_path=Path("/tmp/out.mp4"),
    )
    assert cmd.count("-i") == 3
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v][1:v]xfade=transition=fade:duration=0.500:offset=7.500[v1]" in filter_complex
    assert "[v1][2:v]xfade=transition=fade:duration=0.500:offset=19.000[vout]" in filter_complex
    assert "[0:a][1:a]acrossfade=duration=0.500[a1]" in filter_complex
    assert "[a1][2:a]acrossfade=duration=0.500[aout]" in filter_complex
    assert cmd[cmd.index("-map") + 1] == "[vout]"
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert "[aout]" in maps


def test_crossfade_concat_command_without_audio_has_no_acrossfade():
    cmd = build_crossfade_concat_command(
        [Path("/tmp/a.mp4"), Path("/tmp/b.mp4")],
        [8.0, 12.0],
        has_audio=False,
        output_path=Path("/tmp/out.mp4"),
    )
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "acrossfade" not in filter_complex
    assert "-an" in cmd
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert "[aout]" not in maps


def test_watermark_filter_complex_default_top_right():
    fragment = build_watermark_filter_complex("0:v", 2, "top_right")
    assert "[2:v]format=rgba" in fragment
    assert "colorchannelmixer=aa=0.8" in fragment
    assert "[0:v][wm]overlay=x=main_w-w-24:y=24[vwatermark]" in fragment


def test_watermark_filter_complex_unknown_position_falls_back_to_default():
    fragment = build_watermark_filter_complex("0:v", 1, "center-ish-nonsense")
    assert "x=main_w-w-24:y=24" in fragment


def test_final_encode_command_mp4_codecs():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"), None, None, "mp4", has_audio=True, output_path=Path("/tmp/out.mp4")
    )
    assert "libx264" in cmd
    assert "aac" in cmd
    assert "-vf" not in cmd  # no captions


def test_final_encode_command_webm_uses_vp9_and_opus():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"), None, None, "webm", has_audio=True, output_path=Path("/tmp/out.webm")
    )
    assert "libvpx-vp9" in cmd
    assert "libopus" in cmd
    assert "libx264" not in cmd


def test_final_encode_command_no_audio_adds_an():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"), None, None, "mp4", has_audio=False, output_path=Path("/tmp/out.mp4")
    )
    assert "-an" in cmd
    assert "aac" not in cmd


def test_final_encode_command_burns_captions_when_provided():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"),
        Path("/tmp/captions.ass"),
        None,
        "mp4",
        has_audio=True,
        output_path=Path("/tmp/out.mp4"),
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert "ass=" in vf
    assert "/tmp/captions.ass" in vf


def test_final_encode_command_unknown_format_falls_back_to_mp4_codecs():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"), None, None, "avi", has_audio=True, output_path=Path("/tmp/out.avi")
    )
    assert "libx264" in cmd


def test_final_encode_command_with_music_and_dialogue_mixes_and_keeps_dialogue_full_volume():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"),
        None,
        Path("/tmp/music.m4a"),
        "mp4",
        has_audio=True,
        output_path=Path("/tmp/out.mp4"),
    )
    assert cmd[cmd.index("-i") + 1] == "/tmp/in.mp4"
    # music is the second input
    assert cmd.count("-i") == 2
    assert "/tmp/music.m4a" in cmd
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "[1:a]volume=0.25[music]" in filter_complex
    # normalize=0 is load-bearing -- see build_final_encode_command's docstring
    assert "normalize=0" in filter_complex
    assert "[0:a][music]amix=inputs=2:duration=first" in filter_complex
    assert "-map" in cmd
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert "[aout]" in maps
    assert "0:v" in maps
    assert "aac" in cmd  # dialogue present -> normal audio codec, not -an


def test_final_encode_command_with_music_and_captions_chains_both_filters():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"),
        Path("/tmp/captions.ass"),
        Path("/tmp/music.m4a"),
        "mp4",
        has_audio=True,
        output_path=Path("/tmp/out.mp4"),
    )
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v]ass=" in filter_complex
    assert "[vcap]" in filter_complex
    assert "amix" in filter_complex
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert "[vcap]" in maps
    assert "[aout]" in maps


def test_final_encode_command_with_music_and_no_dialogue_audio_uses_music_directly():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"),
        None,
        Path("/tmp/music.m4a"),
        "mp4",
        has_audio=False,
        output_path=Path("/tmp/out.mp4"),
    )
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert "1:a" in maps  # music stream used directly, no mixing needed
    assert "aac" in cmd  # still has an audio codec (the music track)
    assert "-an" not in cmd
    # no amix necessary when there's nothing to mix music with
    if "-filter_complex" in cmd:
        assert "amix" not in cmd[cmd.index("-filter_complex") + 1]


def test_final_encode_command_with_watermark_composites_last():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"),
        Path("/tmp/captions.ass"),
        None,
        "mp4",
        watermark_path=Path("/tmp/logo.png"),
        has_audio=True,
        output_path=Path("/tmp/out.mp4"),
    )
    assert "/tmp/logo.png" in cmd
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v]ass=" in filter_complex  # captions run before watermark
    assert "[vcap][wm]overlay=" in filter_complex
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert "[vwatermark]" in maps


def test_final_encode_command_with_broll_requires_output_dims():
    spec = BrollSpec(image_input_index=0, start=1.0, end=3.0)
    with pytest.raises(ValueError, match="broll_out_width"):
        build_final_encode_command(
            Path("/tmp/in.mp4"),
            None,
            None,
            "mp4",
            broll_specs=[spec],
            broll_image_paths=[Path("/tmp/broll.jpg")],
            has_audio=True,
            output_path=Path("/tmp/out.mp4"),
        )


def test_final_encode_command_with_mismatched_broll_lists_raises():
    spec = BrollSpec(image_input_index=0, start=1.0, end=3.0)
    with pytest.raises(ValueError, match="same length"):
        build_final_encode_command(
            Path("/tmp/in.mp4"),
            None,
            None,
            "mp4",
            broll_specs=[spec],
            broll_image_paths=[],
            broll_out_width=1080,
            broll_out_height=1920,
            has_audio=True,
            output_path=Path("/tmp/out.mp4"),
        )


def test_final_encode_command_with_watermark_and_no_audio_has_no_audio_map():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"),
        None,
        None,
        "mp4",
        watermark_path=Path("/tmp/logo.png"),
        has_audio=False,
        output_path=Path("/tmp/out.mp4"),
    )
    assert "-an" in cmd
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert len(maps) == 1  # only the video map, no audio map at all


def test_final_encode_command_with_broll_appends_image_input_and_overlay():
    spec = BrollSpec(image_input_index=0, start=1.0, end=3.0)
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"),
        None,
        None,
        "mp4",
        broll_specs=[spec],
        broll_image_paths=[Path("/tmp/broll.jpg")],
        broll_out_width=1080,
        broll_out_height=1920,
        has_audio=True,
        output_path=Path("/tmp/out.mp4"),
    )
    assert "/tmp/broll.jpg" in cmd
    assert "-loop" in cmd
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "zoompan" in filter_complex
    assert "[vbroll]" in filter_complex
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert "[vbroll]" in maps


def test_full_video_render_command_composes_crop_scale_captions_music_watermark():
    spec = BrollSpec(image_input_index=0, start=5.0, end=8.0)
    cmd = build_full_video_render_command(
        Path("/tmp/source.mp4"),
        CropParams(width=1080, height=1080, x=100, y=0),
        OutputDimensions(1080, 1920),
        Path("/tmp/captions.ass"),
        Path("/tmp/music.m4a"),
        "mp4",
        broll_specs=[spec],
        broll_image_paths=[Path("/tmp/broll.jpg")],
        watermark_path=Path("/tmp/logo.png"),
        has_audio=True,
        output_path=Path("/tmp/out.mp4"),
    )
    assert cmd[cmd.index("-i") + 1] == "/tmp/source.mp4"
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "crop=1080:1080:100:0" in filter_complex
    assert "scale=1080:1920[vscaled]" in filter_complex
    assert "zoompan" in filter_complex
    assert "ass=" in filter_complex
    assert "overlay=x=main_w-w-24" in filter_complex
    assert "amix" in filter_complex
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert "[vwatermark]" in maps
    assert "[aout]" in maps
    # full-video mode uses the faster preset, not highlight-reel's "medium"
    assert "faster" in cmd


def test_full_video_render_command_with_music_and_no_dialogue_audio_uses_music_directly():
    cmd = build_full_video_render_command(
        Path("/tmp/source.mp4"),
        CropParams(width=100, height=100, x=0, y=0),
        OutputDimensions(100, 100),
        None,
        Path("/tmp/music.m4a"),
        "mp4",
        has_audio=False,
        output_path=Path("/tmp/out.mp4"),
    )
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    assert "1:a" in maps  # music stream used directly, no mixing needed
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "amix" not in filter_complex


def test_full_video_render_command_no_audio_no_extras_is_minimal():
    cmd = build_full_video_render_command(
        Path("/tmp/source.mp4"),
        CropParams(width=100, height=100, x=0, y=0),
        OutputDimensions(100, 100),
        None,
        None,
        "mp4",
        has_audio=False,
        output_path=Path("/tmp/out.mp4"),
    )
    assert cmd.count("-i") == 1
    assert "-an" in cmd
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "crop=100:100:0:0" in filter_complex
    assert "amix" not in filter_complex
