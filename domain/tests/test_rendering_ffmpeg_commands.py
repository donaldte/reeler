from pathlib import Path

from domain.rendering.dto import ClipSpec, CropParams, OutputDimensions
from domain.rendering.ffmpeg_commands import (
    build_concat_command,
    build_concat_list_content,
    build_extract_clip_command,
    build_final_encode_command,
)


def test_extract_clip_command_basic_shape():
    cmd = build_extract_clip_command(
        Path("/media/source.mp4"),
        ClipSpec(start=10.0, end=20.0, rank=1),
        CropParams(width=1080, height=1080, x=100, y=0),
        OutputDimensions(1080, 1920),
        has_audio=True,
        apply_fade=False,
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
    assert "fade" not in vf
    assert "-c:a" in cmd and "aac" in cmd
    assert cmd[-1] == "/tmp/clip_000.mp4"


def test_extract_clip_command_no_audio_adds_an_flag():
    cmd = build_extract_clip_command(
        Path("/media/source.mp4"),
        ClipSpec(start=0.0, end=5.0, rank=1),
        CropParams(width=100, height=100, x=0, y=0),
        OutputDimensions(100, 100),
        has_audio=False,
        apply_fade=False,
        output_path=Path("/tmp/clip.mp4"),
    )
    assert "-an" in cmd
    assert "-c:a" not in cmd


def test_extract_clip_command_with_fade_adds_video_and_audio_fade_filters():
    cmd = build_extract_clip_command(
        Path("/media/source.mp4"),
        ClipSpec(start=0.0, end=10.0, rank=1),
        CropParams(width=100, height=100, x=0, y=0),
        OutputDimensions(100, 100),
        has_audio=True,
        apply_fade=True,
        output_path=Path("/tmp/clip.mp4"),
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert "fade=t=in:st=0:d=0.3" in vf
    assert "fade=t=out:st=9.700:d=0.3" in vf
    af = cmd[cmd.index("-af") + 1]
    assert "afade=t=in" in af
    assert "afade=t=out" in af


def test_extract_clip_command_fade_without_audio_has_no_af_flag():
    cmd = build_extract_clip_command(
        Path("/media/source.mp4"),
        ClipSpec(start=0.0, end=10.0, rank=1),
        CropParams(width=100, height=100, x=0, y=0),
        OutputDimensions(100, 100),
        has_audio=False,
        apply_fade=True,
        output_path=Path("/tmp/clip.mp4"),
    )
    assert "-af" not in cmd
    assert "-an" in cmd


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


def test_final_encode_command_mp4_codecs():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"), None, "mp4", has_audio=True, output_path=Path("/tmp/out.mp4")
    )
    assert "libx264" in cmd
    assert "aac" in cmd
    assert "-vf" not in cmd  # no captions


def test_final_encode_command_webm_uses_vp9_and_opus():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"), None, "webm", has_audio=True, output_path=Path("/tmp/out.webm")
    )
    assert "libvpx-vp9" in cmd
    assert "libopus" in cmd
    assert "libx264" not in cmd


def test_final_encode_command_no_audio_adds_an():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"), None, "mp4", has_audio=False, output_path=Path("/tmp/out.mp4")
    )
    assert "-an" in cmd
    assert "aac" not in cmd


def test_final_encode_command_burns_captions_when_provided():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"),
        Path("/tmp/captions.ass"),
        "mp4",
        has_audio=True,
        output_path=Path("/tmp/out.mp4"),
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert "ass=" in vf
    assert "/tmp/captions.ass" in vf


def test_final_encode_command_unknown_format_falls_back_to_mp4_codecs():
    cmd = build_final_encode_command(
        Path("/tmp/in.mp4"), None, "avi", has_audio=True, output_path=Path("/tmp/out.avi")
    )
    assert "libx264" in cmd
